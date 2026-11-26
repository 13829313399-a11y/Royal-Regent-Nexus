"""Reusable Calc worker. Its parent supplies generated report paths over a private pipe."""
import ctypes
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


# Stable prefixes of the public LibreOfficeKit office/document C interfaces.
Pointer = ctypes.c_void_p
String = ctypes.c_char_p
Destroy = ctypes.CFUNCTYPE(None, Pointer)


class OfficeMethods(ctypes.Structure):
    _fields_ = [('size', ctypes.c_size_t), ('destroy', Destroy),
                ('load', ctypes.CFUNCTYPE(Pointer, Pointer, String))]


class DocumentMethods(ctypes.Structure):
    _fields_ = [('size', ctypes.c_size_t), ('destroy', Destroy),
                ('save_as', ctypes.CFUNCTYPE(ctypes.c_int, Pointer, String, String, String))]


def methods(handle, interface):
    return ctypes.cast(handle, ctypes.POINTER(ctypes.POINTER(interface))).contents.contents


def convert(office, source):
    document = methods(office, OfficeMethods).load(office, source.as_uri().encode())
    if not document:
        raise RuntimeError('无法读取工作簿')
    api = methods(document, DocumentMethods)
    try:
        target = source.with_suffix('.html').as_uri().encode()
        if not api.save_as(document, target, b'html', None):
            raise RuntimeError('无法生成工作簿预览')
    finally:
        api.destroy(document)


def main(library_path, program, folder):
    if sys.platform == 'darwin':
        os.environ['URE_BOOTSTRAP'] = 'vnd.sun.star.pathname:' + str(program.parent/'Resources/fundamentalrc')
    os.environ['SAL_USE_VCLPLUGIN'] = 'svp'
    library = ctypes.CDLL(str(library_path), mode=ctypes.RTLD_GLOBAL)
    initialize = library.libreofficekit_hook_2
    initialize.argtypes = [String, String]
    initialize.restype = Pointer
    profile = folder/'profile'
    fonts = profile/'user/fonts'
    fonts.mkdir(parents=True)
    font = Path('/System/Library/Fonts/STHeiti Medium.ttc')
    if font.is_file():
        (fonts/font.name).symlink_to(font)
    office = initialize(os.fsencode(program), profile.as_uri().encode())
    if not office:
        raise RuntimeError('无法启动预览转换引擎')
    try:
        print('ready', flush=True)
        for line in sys.stdin:
            try:
                convert(office, Path(json.loads(line)))
            except Exception:
                print('error', flush=True)
            else:
                print('ok', flush=True)
    finally:
        methods(office, OfficeMethods).destroy(office)


if __name__ == '__main__':
    with TemporaryDirectory(prefix='qc-preview-office-') as tmp:
        main(Path(sys.argv[1]), Path(sys.argv[2]), Path(tmp))
