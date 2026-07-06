#!/usr/bin/env python3
"""
HTML Format - 单行 HTML 格式化工具
支持: web-clone JSON包装 / SingleFile base64 / 普通minified / DOM序列化
用法: python3 format.py [目录路径|文件路径...]
      python3 format.py .                    # 当前目录下所有 .html
      python3 format.py /path/to/dir         # 指定目录下所有 .html
      python3 format.py a.html b.html        # 指定文件
"""

import json, re, glob, subprocess, sys, os

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
    '<h1', '<h2', '<h3', '<h4', '<h5', '<h6', '<p', '<title',
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
    """检测 HTML 格式类型"""
    head = raw[:200]
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


def try_prettier(files_to_format):
    """尝试 prettier 格式化，成功返回 True"""
    try:
        result = subprocess.run(
            ['npx', 'prettier', '--write', '--parser', 'html',
             '--print-width', '120'] + files_to_format,
            capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception:
        return False


def format_files(targets):
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

    # 输出结果
    print('\n=== 格式化完成 ===')
    for fname in files:
        with open(fname, 'r') as f:
            content = f.read()
        lines = content.count('\n') + 1
        size = len(content)
        print(f'  {os.path.basename(fname)}: {lines:,} lines, {size:,} bytes')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 format.py <directory|file.html> [...]')
        print('  python3 format.py .              # 当前目录所有 .html')
        print('  python3 format.py /path/to/dir   # 指定目录')
        print('  python3 format.py a.html b.html  # 指定文件')
        sys.exit(1)
    format_files(sys.argv[1:])
