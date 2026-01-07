import json
import os
from pathlib import Path
import polib

# 获取当前目录
current_dir = Path(__file__).parent

# 读取JSON语言文件
def read_json_file(locale):
    json_path = current_dir / f"{locale.replace('_', '-')}.json"
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# 创建PO文件
def create_po_file(locale, translations):
    # 创建PO文件对象
    po = polib.POFile()
    po.metadata = {
        'Project-Id-Version': '1.0',
        'Report-Msgid-Bugs-To': 'your-email@example.com',
        'POT-Creation-Date': '2024-01-01 00:00+0000',
        'PO-Revision-Date': '2024-01-01 00:00+0000',
        'Last-Translator': 'Your Name <your-email@example.com>',
        'Language-Team': f'{locale} <your-email@example.com>',
        'Language': locale,
        'MIME-Version': '1.0',
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Transfer-Encoding': '8bit',
    }
    
    # 添加翻译条目
    for msgid, msgstr in translations.items():
        entry = polib.POEntry(
            msgid=msgid,
            msgstr=msgstr,
            occurrences=[(f'messages.pot', '0')],
        )
        po.append(entry)
    
    # 保存PO文件
    locales_dir = current_dir / "locales"
    po_dir = locales_dir / locale / "LC_MESSAGES"
    po_dir.mkdir(parents=True, exist_ok=True)
    po_path = po_dir / "messages.po"
    po.save(str(po_path))
    print(f"Created PO file: {po_path}")
    
    # 编译为MO文件
    mo_path = po_dir / "messages.mo"
    po.save_as_mofile(str(mo_path))
    print(f"Created MO file: {mo_path}")

# 主函数
def main():
    # 支持的语言
    locales = ["zh_CN", "en_US"]
    
    # 转换每个语言文件
    for locale in locales:
        print(f"Processing {locale}...")
        translations = read_json_file(locale)
        if translations:
            create_po_file(locale, translations)
        else:
            print(f"No translations found for {locale}")

if __name__ == "__main__":
    main()
