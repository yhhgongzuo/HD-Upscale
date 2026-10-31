"""Portable fixed ART processing. No image-generation API calls or downloads."""
import argparse
import base64
import hashlib
import io
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

from PIL import Image, ImageCms, ImageDraw, ImageOps

APPROVED_HASHES = {
    'fixed.arp': '511e2747e7ac07f5ea951bd0247a564acb21fec965197ac49fac856318ef084e',
    'fixed.json': '15065c7854efb5729a2f1e93ecb4bf414a67a181846282eeb5b127daba28773b',
}
MAX_PIXELS = 50_000_000
MAX_BYTES = 80 * 1024 * 1024


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def even(value):
    n = int(round(value))
    return max(2, n - n % 2)


def dimensions(width, height, mode):
    if width < 1 or height < 1:
        raise ValueError('图片宽高必须为正整数。')
    if mode == 'universal':
        result = (width * 2, height * 2)
    elif max(width, height) == 4096:
        result = (width, height)
    elif width >= height:
        result = (4096, even(4096 * height / width))
    else:
        result = (even(4096 * width / height), 4096)
    if math.prod(result) > MAX_PIXELS:
        raise ValueError(f'放大后为 {result[0]}×{result[1]}，超过固定增强模块的五千万像素上限。请先调整首轮生成方案，不能静默缩小或跳过增强。')
    return result


def enhance(context, source, output):
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('缩放后的 PNG 超过增强模块 80 MiB 输入上限。')
    for name, expected in APPROVED_HASHES.items():
        if sha(context['preset'] / name) != expected:
            raise ValueError('固定增强预设校验失败，不允许使用已修改的预设。')
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with tempfile.TemporaryDirectory(prefix='ahui-art-', dir=context['state']) as td:
        work = Path(td)
        with Image.open(source) as src:
            if src.width * src.height > MAX_PIXELS:
                raise ValueError('图片超过五千万像素。')
            src.load()
            im = ImageOps.exif_transpose(src)
            has_alpha = 'A' in im.getbands() or 'transparency' in im.info
            alpha = im.convert('RGBA').getchannel('A') if has_alpha else None
            icc = im.info.get('icc_profile')
            rgb = im.convert('RGB')
            if icc:
                color_source = im if im.mode in ('RGB', 'CMYK', 'LAB') else rgb
                rgb = ImageCms.profileToProfile(color_source, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
            size = rgb.size
            rgb.save(work / 'input.png', icc_profile=srgb)
        for name in ('settings', 'cache'):
            (work / name).mkdir()
        env = os.environ.copy()
        env.update(ART_SETTINGS=str(work / 'settings'), ART_CACHE=str(work / 'cache'), OMP_NUM_THREADS=str(min(8, os.cpu_count() or 4)))
        target = work / 'result.png'
        engine = context['engine']
        # Match official launchers without their unquoted dirname expansion.
        if context['key'].startswith('linux-'):
            env.update(ART_restore_GIO_MODULE_DIR=env.get('GIO_MODULE_DIR', ''), ART_restore_LD_LIBRARY_PATH=env.get('LD_LIBRARY_PATH', ''))
            env.update(GIO_MODULE_DIR=str(engine.parent / 'lib/gio/modules'), LD_LIBRARY_PATH=str(engine.parent / 'lib'), ART_EXIFTOOL_BASE_DIR=str(engine.parent / 'lib/exiftool'))
            engine = engine.parent / '.ART-cli.bin'
        elif context['key'].startswith('macos-'):
            contents = engine.parent.parent
            env.update(ART_restore_GIO_MODULE_DIR=env.get('GIO_MODULE_DIR', ''), ART_restore_DYLD_LIBRARY_PATH=env.get('DYLD_LIBRARY_PATH', ''))
            env.update(DYLD_LIBRARY_PATH=str(contents / 'Frameworks'), ART_EXIFTOOL_BASE_DIR=str(contents / 'Resources/exiftool'))
            engine = engine.parent / '.ART-cli.bin'
        command = [str(engine), '-q', '-a', '-o', str(target), '-p', str(context['preset'] / 'fixed.arp'), '-n', '-b8', '-c', str(work / 'input.png')]
        proc = subprocess.run(command, cwd=engine.parent, env=env, capture_output=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode or not target.is_file():
            detail = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')[-2000:]
            raise RuntimeError('ART 固定增强失败；请检查系统动态库或执行权限：' + detail)
        with Image.open(target) as rendered:
            rendered.load()
            if rendered.size != size:
                raise RuntimeError('ART 返回了非预期尺寸。')
            if alpha is not None:
                result = rendered.convert('RGBA')
                result.putalpha(alpha)
                result.save(target, icc_profile=rendered.info.get('icc_profile', srgb))
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as out, target.open('rb') as source_stream:
            import shutil
            shutil.copyfileobj(source_stream, out)


def run(context, source, output, mode):
    start = time.perf_counter()
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.suffix.lower() != '.png' or output.exists() or source == output:
        raise ValueError('输出必须是不存在的新 PNG 文件，不能覆盖原图或已有文件。')
    source_hash = sha(source)
    with tempfile.TemporaryDirectory(prefix='ahui-scale-', dir=context['state']) as td:
        scaled = Path(td) / 'scaled.png'
        with Image.open(source) as src:
            if src.format not in ('JPEG', 'PNG', 'WEBP', 'TIFF'):
                raise ValueError('支持 JPG、PNG、WebP、TIFF。')
            if getattr(src, 'n_frames', 1) > 1:
                raise ValueError('请先选择动画或多页文件中的单张图片。')
            # Check target size before decoding large pixel buffers.
            width, height = src.size
            if src.getexif().get(274, 1) in (5, 6, 7, 8):
                width, height = height, width
            target_size = dimensions(width, height, mode)
            if src.width * src.height > MAX_PIXELS:
                raise ValueError('生成图本身超过五千万像素，无法安全进入固定增强流程。')
            oriented = ImageOps.exif_transpose(src)
            original_size = oriented.size
            target_size = dimensions(*original_size, mode)
            alpha = 'A' in oriented.getbands() or 'transparency' in oriented.info
            im = oriented.convert('RGBA' if alpha else 'RGB')
            profile = oriented.info.get('icc_profile')
            if profile:
                color_source = oriented if oriented.mode in ('RGB', 'CMYK', 'LAB') else im.convert('RGB')
                rgb = ImageCms.profileToProfile(color_source, ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile('sRGB'), outputMode='RGB')
                if alpha:
                    rgb = rgb.convert('RGBA')
                    rgb.putalpha(im.getchannel('A'))
                im = rgb
            if im.size != target_size:
                im = im.resize(target_size, Image.Resampling.LANCZOS)
            save_kwargs = {}
            if profile:
                save_kwargs['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
            im.save(scaled, **save_kwargs)
        enhance(context, scaled, output)
    with Image.open(output) as final:
        final.load()
        if final.size != target_size or final.format != 'PNG':
            raise RuntimeError('成品尺寸或格式验证失败。')
        if alpha and 'A' not in final.getbands():
            raise RuntimeError('成品透明通道缺失。')
    if sha(source) != source_hash:
        raise RuntimeError('源文件校验异常。')
    return {'ok': True, 'output': str(output), 'mode': mode, 'input_size': original_size, 'output_size': target_size, 'alpha_preserved': alpha, 'source_unchanged': True, 'seconds': round(time.perf_counter()-start, 2)}


def image_payload(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    data = buffer.getvalue()
    return {'src': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii'), 'sha256': hashlib.sha256(data).hexdigest()}


def preview(context, before, after, output):
    before, after, output = Path(before).resolve(), Path(after).resolve(), Path(output).resolve()
    if output.exists() or output.suffix.lower() != '.html':
        raise ValueError('对比页必须是不存在的新 HTML 文件。')
    with Image.open(after) as finished:
        finished.load()
        if finished.format != 'PNG':
            raise ValueError('成品必须是 PNG。')
        target = finished.size
    with Image.open(before) as original:
        im = ImageOps.exif_transpose(original)
        original_size = im.size
        ratio_error = abs(im.width / im.height / (target[0] / target[1]) - 1)
        if ratio_error > 0.005:
            raise ValueError('原图与成品比例不一致，不能拉伸原图伪造对齐对比。')
        im = im.convert('RGBA' if 'A' in im.getbands() or 'transparency' in im.info else 'RGB')
        before_data = image_payload(im.resize(target, Image.Resampling.LANCZOS))
    content = after.read_bytes()
    data = {'before': before_data, 'after': {'src': 'data:image/png;base64,'+base64.b64encode(content).decode('ascii'), 'sha256': hashlib.sha256(content).hexdigest()}, 'beforeOriginalSize': original_size}
    folder = {'folderPath': str(after.parent), 'afterName': after.name}
    template = (context['root'] / 'assets/preview/template.html').read_text(encoding='utf-8')
    page = template.replace('__IMAGE_DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')).replace('__FOLDER_DATA__', json.dumps(folder, ensure_ascii=False).replace('<', '\\u003c'))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        f.write(page)
    return {'ok': True, 'html': str(output), 'self_contained': True, 'afterBytesPreserved': True, 'beforeResizedTo': target, 'originalSize': original_size}


def doctor(context, capabilities):
    with tempfile.TemporaryDirectory(prefix='ahui-doctor-', dir=context['state']) as td:
        work = Path(td)
        source = work / 'test.png'
        im = Image.new('RGBA', (129, 87), (120, 180, 210, 110))
        draw = ImageDraw.Draw(im)
        draw.rectangle((12, 12, 74, 64), fill=(60, 90, 150, 255))
        im.save(source)
        output = work / 'result.png'
        result = run(context, source, output, 'universal')
        with Image.open(output) as final:
            expected = im.resize((258, 174), Image.Resampling.LANCZOS).getchannel('A').tobytes()
            if final.getchannel('A').tobytes() != expected:
                raise RuntimeError('透明通道自检失败。')
        try:
            run(context, source, output, 'universal')
        except ValueError:
            pass
        else:
            raise RuntimeError('禁止覆盖自检失败。')
        preview(context, source, output, work / 'comparison.html')
    provider = None
    ready = False
    if capabilities:
        provider = json.loads(Path(capabilities).read_text(encoding='utf-8-sig'))
        ready = (provider.get('image_edit') is True and provider.get('result_access') is True and all(isinstance(provider.get(k), str) and provider[k].strip() for k in ('host', 'provider', 'evidence')))
        if not ready:
            raise ValueError('生图能力记录不完整或未核实；不能启用技能。')
    return {'ok': True, 'ready': ready, 'installation_status': 'local_checks_passed_registration_required' if ready else 'needs_image_provider_verification', 'platform': context['key'], 'engine': str(context['engine']), 'offline_processing_test': 'passed', 'alpha_test': 'passed', 'no_overwrite_test': 'passed', 'preview_build_test': 'passed', 'image_generation_tested': False, 'provider_verified_by_agent': bool(provider), 'tested_size': result['output_size']}


def main(context):
    parser = argparse.ArgumentParser(description='阿辉的高清放大 Skill 离线处理工具')
    subs = parser.add_subparsers(dest='command', required=True)
    doc = subs.add_parser('doctor')
    doc.add_argument('--capabilities', type=Path)
    size = subs.add_parser('size', help='保留豆包原版尺寸计算规则')
    size.add_argument('--image', type=Path, required=True)
    size.add_argument('--model', default='seedream_5.0_pro')
    size.add_argument('--tier', default='auto')
    plan = subs.add_parser('plan')
    plan.add_argument('--width', type=int, required=True)
    plan.add_argument('--height', type=int, required=True)
    plan.add_argument('--mode', choices=('universal', 'doubao'), default='universal')
    proc = subs.add_parser('run')
    proc.add_argument('--input', type=Path, required=True)
    proc.add_argument('--output', type=Path, required=True)
    proc.add_argument('--mode', choices=('universal', 'doubao'), default='universal')
    prev = subs.add_parser('preview')
    prev.add_argument('--before', type=Path, required=True)
    prev.add_argument('--after', type=Path, required=True)
    prev.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'doctor':
        result = doctor(context, args.capabilities)
    elif args.command == 'size':
        path = context['root'] / 'assets/legacy-doubao/scripts/post_process.py'
        spec = importlib.util.spec_from_file_location('ahui_legacy_size', path)
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        result = legacy.calc_size(args.image, args.model, args.tier)
    elif args.command == 'plan':
        result = {'ok': True, 'input_size': [args.width, args.height], 'output_size': dimensions(args.width, args.height, args.mode), 'mode': args.mode, 'file_size_checked_after_resize': True}
    elif args.command == 'run':
        result = run(context, args.input, args.output, args.mode)
    else:
        result = preview(context, args.before, args.after, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0
