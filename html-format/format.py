#!/usr/bin/env python3
"""
HTML Format - 单行 HTML 格式化工具
支持: web-clone JSON包装 / SingleFile base64 / 普通minified / DOM序列化
用法: python3 format.py [选项] [目录路径|文件路径...]
      python3 format.py .                    # 当前目录下所有 .html
      python3 format.py /path/to/dir         # 指定目录下所有 .html
      python3 format.py a.html b.html        # 指定文件
      python3 format.py --sequential .       # 关闭语义命名，退回纯序号命名

附加能力 (v2.1.0): 自动把 HTML 内联的 base64 图片/字体抽离为独立文件
(images/ 与 fonts/ 子目录)，并把 HTML 中的 data URI 替换为相对路径引用，
大幅减小 HTML 体积。
  文件名默认按上下文语义命名: <img alt> → id/class → rel(icon等) → CSS选择器；
  推断不到时回退为 源文件前缀_序号。可用 --sequential 强制纯序号命名。
  同一目录内按内容 sha256 去重，序号从已有文件最大序号续接，可安全重跑。
"""

import json, re, glob, subprocess, sys, os, base64, hashlib, shutil

VOID_ELEMENTS = ['meta', 'img', 'link', 'br', 'hr', 'input', 'source',
                 'embed', 'area', 'base', 'col', 'track', 'wbr']

BLOCK_CLOSE = ['</html>', '</head>', '</body>', '</div>', '</nav>', '</section>',
    '</header>', '</footer>', '</main>', '</article>', '</aside>',
    '</table>', '</tr>', '</ul>', '</ol>', '</li>', '</form>',
    '</script>', '</style>', '</template>', '</select>', '</textarea>',
    '</noscript>', '</iframe>', '</video>', '</figure>',
    '</blockquote>', '</pre>', '</fieldset>', '</details>', '</summary>',
    '</h1>', '</h2>', '</h3>', '</h4>', '</h5>', '</h6>', '</p>',
    '</title>', '</a>', '</button>', '</label>', '</option>',
    '</span>', '</strong>', '</em>', '</b>', '</i>', '</small>']

BLOCK_OPEN = ['<div', '<nav', '<section', '<header', '<footer', '<main',
    '<article', '<aside', '<table', '<ul', '<ol', '<li', '<form',
    '<script', '<template', '<select', '<noscript', '<iframe',
    '<h1', '<h2', '<h3', '<h4', '<h5', '<h6', '<p', '<title>',
    '<head', '<body', '<meta', '<link', '<br', '<hr', '<input',
    '<style', '<a ', '<img ', '<button', '<label', '<option',
    '<tr', '<td', '<th', '<thead', '<tbody', '<tfoot', '<colgroup',
    '<fieldset', '<legend', '<details', '<summary', '<figure', '<figcaption']

INDENT_TAGS = ['div', 'nav', 'section', 'ul', 'ol', 'li', 'table', 'tr',
    'head', 'body', 'html', 'form', 'header', 'footer', 'main', 'article',
    'aside', 'template', 'select', 'fieldset', 'details', 'figure', 'tbody',
    'thead', 'tfoot', 'colgroup']


def collect_files(targets):
    """从命令行参数收集 HTML 文件列表"""
    files = []
    for t in targets:
        if os.path.isdir(t):
            files.extend(sorted(glob.glob(os.path.join(t, '*.html'))))
        elif os.path.isfile(t) and t.endswith('.html'):
            files.append(t)
    return files


def detect_type(raw):
    """检测 HTML 格式类型

    head 取前 50000 字节：SingleFile 的导出常在前部包含一长串
    <html prefix="..."> 命名空间声明，其 'SingleFile' 标记可能出现得较晚，
    只取 200 字节会把它误判为 Type C（普通 minified），进而用 prettier
    去处理体积巨大的 base64，既慢又容易失败。
    """
    head = raw[:50000]
    if 'Script ran on page' in head:
        return 'A'  # web-clone JSON wrapper
    if 'SingleFile' in head:
        return 'B'  # SingleFile with base64
    if re.search(r'<(meta|img|link|br|hr|input)(\s[^>]*)?></\1>', raw[:5000]):
        return 'D'  # DOM serialization (void elements with closing tags)
    return 'C'  # Standard minified HTML


def extract_json_wrapper(raw):
    """Type A: 从 evaluate_script JSON 包装中提取纯 HTML"""
    idx = raw.find('"<!DOCTYPE html>')
    if idx == -1:
        idx = raw.find('"<html')
    if idx == -1:
        return raw
    end_idx = raw.rfind('"\n```')
    if end_idx == -1:
        return raw
    json_str = raw[idx:end_idx + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return json_str[1:-1].replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')


def fix_void_elements(html):
    """修复 void 元素闭合标签: <meta></meta> → <meta>"""
    for tag in VOID_ELEMENTS:
        html = re.sub(rf'<{tag}(\s[^>]*)?></{tag}>', rf'<{tag}\1>', html)
    return html


def clean_artifacts(html):
    """清理残留: blob URL, 空脚本, 追踪脚本"""
    html = re.sub(r'<script src="blob:https?://[^"]*"></script>\n?', '', html)
    html = re.sub(r'<script>\s*</script>\n?', '', html)
    html = re.sub(r'<script[^>]*cloudflareinsights[^>]*></script>', '', html)
    html = re.sub(r'<script[^>]*email-decode[^>]*></script>', '', html)
    return html


def python_structural_format(html):
    """Type B 兜底: 在标签边界插入换行 + 基本缩进"""
    for tag in BLOCK_CLOSE:
        html = html.replace(tag, tag + '\n')
    for tag in BLOCK_OPEN:
        html = html.replace(tag, '\n' + tag)
    while '\n\n\n' in html:
        html = html.replace('\n\n\n', '\n\n')

    lines = html.split('\n')
    formatted = []
    indent = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        close_count = len(re.findall(
            r'</(' + '|'.join(INDENT_TAGS) + r')>', stripped))
        indent = max(0, indent - close_count)
        formatted.append('  ' * indent + stripped)
        open_count = len(re.findall(
            r'<(' + '|'.join(INDENT_TAGS) + r')[>\s]', stripped))
        indent += open_count
    return '\n'.join(formatted)


# ---- base64 内联资源抽离 (v2.1.0) --------------------------------------------

# 注意 base64 字符类绝不含 \s：未加引号的属性 (如 href=data:...) 在空白处即截止，
# 若把 \s 纳入会导致贪婪吞掉后续属性 (sizes=16x16 / rel=...) 造成解码失败而漏抽。
_B64_PATTERN = re.compile(
    r'data:([a-zA-Z0-9.+-]+)/([a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=]+)')

_B64_IMG_EXT = {
    'jpeg': 'jpg', 'jpg': 'jpg', 'png': 'png', 'gif': 'gif',
    'webp': 'webp', 'bmp': 'bmp', 'x-icon': 'ico',
    'svg+xml': 'svg', 'tiff': 'tif', 'avif': 'avif',
}
_B64_FONT_EXT = {
    'woff2': 'woff2', 'woff': 'woff', 'x-woff': 'woff',
    'truetype': 'ttf', 'x-font-ttf': 'ttf', 'x-font-opentype': 'otf',
    'otf': 'otf', 'ttf': 'ttf', 'sfnt': 'sfnt',
}

# HTML 标签属性解析 (name="v" / name='v' / name=v)
_ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)


def _b64_max_index(d):
    """扫描目录中已有 _NNNN 序号，返回最大序号（重跑续接用）"""
    m = 0
    if os.path.isdir(d):
        for fn in os.listdir(d):
            mm = re.search(r'_(\d{4})\.', fn)
            if mm:
                m = max(m, int(mm.group(1)))
    return m


def _b64_classify(mime_type, subtype):
    if mime_type == 'image':
        return 'images', _B64_IMG_EXT.get(subtype.lower(), subtype.lower())
    if mime_type == 'font' or (mime_type == 'application' and 'font' in subtype.lower()):
        return 'fonts', _B64_FONT_EXT.get(subtype.lower(), 'font')
    return None, None


def _b64_try_decode(raw):
    """base64 解码，带去空白与补 padding 兜底。失败返回 None。"""
    raw = re.sub(r'\s', '', raw)
    try:
        return base64.b64decode(raw, validate=False)
    except Exception:
        if len(raw) % 4 != 0:
            for _ in range(4 - (len(raw) % 4)):
                try:
                    return base64.b64decode(raw + '=', validate=False)
                except Exception:
                    raw = raw + '='
                    break
        return None


# ---- 语义命名 (v2.1.0) -------------------------------------------------------

def _slugify(hint):
    """把上下文线索清洗为安全文件名片段（小写、限长 40）。

    保留字母/数字/下划线/中日韩汉字与连字符；其余（空格、/、:、. 等）统一
    替换为连字符。空结果返回 ''（调用方回退到序号命名）。
    """
    s = (hint or '').strip()
    if not s:
        return ''
    # 去掉 CSS 选择器等场景里无意义的引号/括号
    s = re.sub(r'[^\w\u3400-\u9fff\-]+', '-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    if len(s) > 40:
        s = s[:40].rstrip('-')
    return s.lower()


def _rel_friendly(rel):
    """把 rel 属性映射为可读的语义名。"""
    r = (rel or '').lower()
    if 'apple-touch-icon' in r:
        return 'apple-touch-icon'
    if 'mask-icon' in r:
        return 'mask-icon'
    if 'icon' in r:
        return 'favicon'
    return re.sub(r'\s+', '-', r) or 'icon'


def _html_attr_hint(html, pos):
    """从包含 pos 的 HTML 标签属性推断命名线索: alt > id > class > rel。"""
    tag_open = html.rfind('<', 0, pos)
    if tag_open == -1:
        return None
    tag_close = html.find('>', pos)
    if tag_close == -1:
        return None
    tag = html[tag_open:tag_close + 1]
    attrs = {}
    for mm in _ATTR_RE.finditer(tag):
        key = mm.group(1).lower()
        val = mm.group(3) or mm.group(4) or mm.group(5) or ''
        attrs[key] = val
    if attrs.get('alt', '').strip():
        return attrs['alt'].strip()
    if attrs.get('id', '').strip():
        return attrs['id'].strip()
    if attrs.get('class', '').strip():
        return attrs['class'].split()[0]  # 取第一个 class
    if attrs.get('rel', '').strip():
        return _rel_friendly(attrs['rel'])
    return None


def _font_face_hint(html, brace, pos):
    """@font-face 块内的字体 → 用 font-family(+weight/style) 命名。

    形如 @font-face{font-family:"Noto Sans TC";font-weight:100;src:url(data:...)}
    直接拿 '@font-face' 当名字毫无信息量，改成 noto-sans-tc-100 更可读。
    """
    decl = html[brace + 1:pos]
    fam = re.search(r'font-family\s*:\s*(["\']?)([^"\';}]+)\1', decl)
    if not fam:
        return None
    name = fam.group(2).strip()
    if not name:
        return None
    w = re.search(r'font-weight\s*:\s*([^;}]+)', decl)
    if w and w.group(1).strip().lower() not in ('', 'normal'):
        name += '-' + w.group(1).strip()
    s = re.search(r'font-style\s*:\s*([^;}]+)', decl)
    if s and s.group(1).strip().lower() not in ('', 'normal'):
        name += '-' + s.group(1).strip()
    return name


def _css_selector_hint(html, pos):
    """若 pos 处于 <style> 块内的 background-image: url(data:...)，取 CSS 选择器。"""
    style_open = html.rfind('<style', 0, pos)
    if style_open == -1:
        return None
    style_close = html.find('</style>', pos)
    if style_close != -1 and pos > style_close:
        return None  # pos 不在该 <style> 内
    brace = html.rfind('{', 0, pos)
    if brace == -1 or brace < style_open:
        return None
    style_tag_close = html.find('>', style_open)
    if style_tag_close == -1 or brace <= style_tag_close:
        return None
    prev = html.rfind('}', style_tag_close, brace)
    start = prev + 1 if prev != -1 else style_tag_close + 1
    sel = html[start:brace]
    sel = re.sub(r'/\*.*?\*/', '', sel, flags=re.S)  # 去 CSS 注释
    sel = sel.strip()
    if not sel:
        return None
    if '@font-face' in sel:
        return _font_face_hint(html, brace, pos) or sel
    return sel


def guess_name(html, pos):
    """综合上下文推断语义文件名（不保证非空）。"""
    hint = _html_attr_hint(html, pos)
    if hint:
        return hint
    return _css_selector_hint(html, pos)


def extract_base64_assets(files, semantic=True):
    """抽离所有 HTML 中的 base64 图片/字体为独立文件并替换引用。

    按每个 HTML 文件所在目录创建 images/ 与 fonts/ 子目录；引用使用相对路径。
    同一目录内按内容 sha256 去重（共享同一份文件）；counter 从已有文件最大
    序号续接，因此可安全重跑、不会覆盖已抽取资源。
    semantic=True 时文件名优先按上下文语义命名（alt>id/class>rel>CSS选择器），
    推断不到再回退 源前缀_序号；semantic=False 直接纯序号命名。
    没有任何内联 base64 的文件会被直接跳过，不做多余写盘。
    """
    by_dir = {}
    for fname in files:
        d = os.path.dirname(os.path.abspath(fname))
        by_dir.setdefault(d, []).append(fname)

    grand_replaced = 0
    grand_created = {'images': 0, 'fonts': 0}
    grand_bytes = {'images': 0, 'fonts': 0}

    for base_dir, flist in by_dir.items():
        img_dir = os.path.join(base_dir, 'images')
        font_dir = os.path.join(base_dir, 'fonts')
        # 目录延迟创建：只有真的要写入该类资源时才 mkdir，
        # 避免在没有字体的站点里留下一个空 fonts/ 目录。
        counter = {'images': _b64_max_index(img_dir),
                   'fonts': _b64_max_index(font_dir)}
        seen = {}        # hash -> 相对路径（本目录内去重）
        used = set()     # 已占用文件名（去重碰撞处理）

        for fname in flist:
            with open(fname, encoding='utf-8', errors='replace') as f:
                html = f.read()
            if _B64_PATTERN.search(html) is None:
                continue  # 无内联 base64，跳过

            prefix = os.path.splitext(os.path.basename(fname))[0]
            orig = len(html.encode('utf-8'))
            parts = []
            last = 0
            replaced = 0
            created = {'images': 0, 'fonts': 0}

            for m in _B64_PATTERN.finditer(html):
                mime_type, subtype, b64 = (
                    m.group(1).lower(), m.group(2).lower(), m.group(3))
                category, ext = _b64_classify(mime_type, subtype)
                if category is None:
                    continue

                data = _b64_try_decode(b64)
                if not data:
                    continue

                h = hashlib.sha256(data).hexdigest()
                if h in seen:
                    rel = seen[h]
                else:
                    rel = None
                    if semantic:
                        hint = guess_name(html, m.start())
                        slug = _slugify(hint) if hint else ''
                        if slug:
                            base = slug
                            cand = f"{base}.{ext}"
                            if cand in used:
                                i = 2
                                while f"{base}-{i}.{ext}" in used:
                                    i += 1
                                base = f"{base}-{i}"
                            rel = f"{category}/{base}.{ext}"
                            used.add(f"{base}.{ext}")
                    if rel is None:  # 回退 / 强制序号
                        counter[category] += 1
                        rel = f"{category}/{prefix}_{counter[category]:04d}.{ext}"
                    out_path = os.path.join(base_dir, rel)
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, 'wb') as out:
                        out.write(data)
                    seen[h] = rel
                    created[category] += 1
                    grand_created[category] += 1
                    grand_bytes[category] += len(data)

                parts.append(html[last:m.start()])
                parts.append(rel)
                last = m.end()
                replaced += 1

            parts.append(html[last:])
            new_html = ''.join(parts)
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(new_html)

            new = len(new_html.encode('utf-8'))
            grand_replaced += replaced
            print(f"🖼️  {os.path.basename(fname)}: {orig:,} → {new:,} bytes "
                  f"(−{orig - new:,}) | 替换 {replaced} 处 "
                  f"(新图片 {created['images']}, 新字体 {created['fonts']})")

    if grand_replaced:
        mode = '语义' if semantic else '序号'
        print(f"\n📊 base64 抽离合计({mode}命名): 替换 {grand_replaced} 处")
        print(f"   图片: {grand_created['images']} 个新文件, "
              f"{grand_bytes['images']/1024/1024:.2f} MB")
        print(f"   字体: {grand_created['fonts']} 个新文件, "
              f"{grand_bytes['fonts']/1024/1024:.2f} MB")
    else:
        print('🖼️  未发现内联 base64 资源，跳过抽离')


# ---- 主流程 -----------------------------------------------------------------

_PRETTIER_CMD = None
_PRETTIER_RESOLVED = False


def _prettier_probe(cmd):
    """探测候选命令是否可真正执行（--version 返回 0）"""
    try:
        r = subprocess.run(cmd + ['--version'],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def resolve_prettier():
    """按优先级定位可用的 prettier，返回命令前缀 list；都不可用返回 None。

    顺序：
      1. 环境变量 PRETTIER_BIN（用户显式指定）
      2. 当前目录 node_modules/.bin/prettier（项目本地依赖）
      3. PATH 上的全局 prettier
      4. npx 缓存中已下载的 prettier（离线可用）
      5. npx --yes prettier（联网下载，最后兜底）

    为什么不直接用 `npx prettier`：npx 每次都会向 registry 解析最新版本，
    缓存里即便有 prettier 也会因版本号不同而重新下载；离线或弱网环境下
    会长时间挂起甚至被系统杀掉，导致格式化整体失败。
    """
    global _PRETTIER_CMD, _PRETTIER_RESOLVED
    if _PRETTIER_RESOLVED:
        return _PRETTIER_CMD
    _PRETTIER_RESOLVED = True

    node = shutil.which('node') or 'node'
    candidates = []

    env_bin = os.environ.get('PRETTIER_BIN')
    if env_bin:
        candidates.append([env_bin])

    local = os.path.join(os.getcwd(), 'node_modules', '.bin', 'prettier')
    if os.path.isfile(local):
        candidates.append([local])

    global_bin = shutil.which('prettier')
    if global_bin:
        candidates.append([global_bin])

    for cached in sorted(glob.glob(os.path.expanduser(
            '~/.npm/_npx/*/node_modules/prettier/bin/prettier.cjs')), reverse=True):
        candidates.append([node, cached])

    candidates.append(['npx', '--yes', 'prettier'])

    for cmd in candidates:
        if _prettier_probe(cmd):
            _PRETTIER_CMD = cmd
            return cmd
    return None


def try_prettier(files_to_format):
    """尝试 prettier 格式化，成功返回 True"""
    cmd = resolve_prettier()
    if cmd is None:
        print('   ⚠️ 未找到可用的 prettier '
              '(已尝试 PRETTIER_BIN / node_modules/.bin / PATH / npx缓存 / npx)')
        return False
    shown = cmd[-1] if len(cmd) > 1 else cmd[0]
    print(f'   使用 prettier: {shown}')
    try:
        result = subprocess.run(
            cmd + ['--write', '--parser', 'html',
                   '--print-width', '120'] + files_to_format,
            capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or '').strip().splitlines()
            if msg:
                print(f'   prettier 报错: {msg[-1][:200]}')
        return result.returncode == 0
    except Exception as e:
        print(f'   prettier 调用异常: {type(e).__name__}: {e}')
        return False


def format_files(targets, semantic=True):
    """主入口：格式化所有目标 HTML 文件"""
    files = collect_files(targets)
    if not files:
        print('No HTML files found.')
        return

    type_map = {'A': [], 'B': [], 'C': [], 'D': []}
    file_contents = {}

    # Phase 1: 读取 + 类型检测
    for fname in files:
        with open(fname, 'r') as f:
            raw = f.read()
        file_contents[fname] = raw
        ftype = detect_type(raw)
        type_map[ftype].append(fname)
        print(f'🔍 {os.path.basename(fname)}: Type {ftype} ({len(raw):,} bytes)')

    print()

    # Phase 2: Type A — JSON 提取
    for fname in type_map['A']:
        raw = file_contents[fname]
        html = extract_json_wrapper(raw)
        file_contents[fname] = html
        print(f'📦 {os.path.basename(fname)}: JSON extracted ({len(raw):,} → {len(html):,} bytes)')

    # Phase 3: Type A + D — void 元素修复
    for fname in type_map['A'] + type_map['D']:
        html = file_contents[fname]
        file_contents[fname] = fix_void_elements(html)
        print(f'🔧 {os.path.basename(fname)}: void elements fixed')

    # Phase 4: 清理残留 (所有类型)
    for fname in files:
        file_contents[fname] = clean_artifacts(file_contents[fname])

    # Phase 5: Type B — Python 结构化 (base64 太重，prettier 处理不了)
    for fname in type_map['B']:
        html = file_contents[fname]
        html = python_structural_format(html)
        file_contents[fname] = html
        lines = html.count('\n') + 1
        print(f'🐍 {os.path.basename(fname)}: Python formatted → {lines:,} lines')

    # Phase 6: 写回文件
    for fname in files:
        with open(fname, 'w') as f:
            f.write(file_contents[fname])

    # Phase 7: Type A + C + D — prettier
    prettier_files = type_map['A'] + type_map['C'] + type_map['D']
    if prettier_files:
        print(f'\n🎨 Running prettier on {len(prettier_files)} files...')
        if try_prettier(prettier_files):
            print('✅ prettier success')
        else:
            print('⚠️ prettier failed, falling back to Python formatting...')
            for fname in prettier_files:
                html = file_contents[fname]
                html = python_structural_format(html)
                with open(fname, 'w') as f:
                    f.write(html)
                lines = html.count('\n') + 1
                print(f'🐍 {os.path.basename(fname)}: Python fallback → {lines:,} lines')

    # Phase 8: 抽离内联 base64 图片/字体 → 独立文件并替换引用
    print('\n🖼️  抽离内联 base64 资源...')
    extract_base64_assets(files, semantic=semantic)

    # 输出结果
    print('\n=== 格式化完成 ===')
    for fname in files:
        with open(fname, 'r') as f:
            content = f.read()
        lines = content.count('\n') + 1
        # 用 UTF-8 字节数，与抽离阶段的口径一致（中文按字符数会明显偏小）
        size = len(content.encode('utf-8'))
        print(f'  {os.path.basename(fname)}: {lines:,} lines, {size:,} bytes')


if __name__ == '__main__':
    args = sys.argv[1:]
    semantic = True
    if '--sequential' in args:
        semantic = False
        args.remove('--sequential')
    if '--no-context' in args:
        semantic = False
        args.remove('--no-context')
    if not args:
        print('Usage: python3 format.py [--sequential] <directory|file.html> [...]')
        print('  python3 format.py .                  # 当前目录所有 .html')
        print('  python3 format.py /path/to/dir       # 指定目录')
        print('  python3 format.py a.html b.html      # 指定文件')
        print('  python3 format.py --sequential .     # 关闭语义命名，纯序号')
        sys.exit(1)
    format_files(args, semantic=semantic)
