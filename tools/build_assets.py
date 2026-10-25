"""Generate the Windows icon and version resource used by the PyInstaller build.

    python tools/build_assets.py <output folder>
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lantern import VERSION  # noqa: E402
from lantern.desktop import tray_image  # noqa: E402

VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Lantern Deck contributors'),
      StringStruct('FileDescription', 'Lantern Deck'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Lantern Deck'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'Lantern Deck.exe'),
      StringStruct('ProductName', 'Lantern Deck'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    tray_image(True, 256).save(out / 'lantern.ico', sizes=[(s, s) for s in sizes])
    nums = tuple(int(p) for p in VERSION.split('.')) + (0,)
    (out / 'version_info.txt').write_text(VERSION_TEMPLATE.format(nums=nums, version=VERSION), encoding='utf-8')
    print(VERSION)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'work')
