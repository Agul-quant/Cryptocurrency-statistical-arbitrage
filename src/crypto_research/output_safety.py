"""Fail-closed destinations for generated files; never follow output symlinks."""
from pathlib import Path
import os


def checked_output_path(root, output, *, directory=False):
    root=Path(root).resolve()
    raw=Path(output).expanduser()
    if '..' in raw.parts:
        raise ValueError('Output must not contain parent-directory traversal')
    target=raw.absolute()
    allowed=root/'local_outputs'
    if target==allowed or not target.is_relative_to(allowed):
        raise ValueError('Output must be inside local_outputs/')
    # Inspect unresolved components, including broken or inward-pointing links.
    for component in (target,*target.parents):
        if not component.is_relative_to(root):break
        if component.is_symlink():
            raise ValueError('Symlink is not allowed in output path: '+str(component))
    if directory and target.exists():
        if not target.is_dir():raise ValueError('Research output must be a directory')
        # All existing descendants are checked before any generated file is opened.
        for current,dirs,files in os.walk(target,followlinks=False):
            for name in dirs+files:
                child=Path(current)/name
                if child.is_symlink():
                    raise ValueError('Symlink is not allowed in output tree: '+str(child))
    resolved=target.resolve()
    if not resolved.is_relative_to(allowed):
        raise ValueError('Output escapes local_outputs/')
    return resolved
