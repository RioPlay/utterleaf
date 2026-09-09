"""Run inside GIMP 3's python-fu-eval batch interpreter, not ordinary Python.

Requires UTTERLEAF_BRAND_ROOT. Originals stay in artifacts/mascot-sources.
Uses an exterior selection so eye glints and speech-balloon interiors survive.
"""
import os
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl
root=Path(os.environ['UTTERLEAF_BRAND_ROOT'])
for name in ('default','listening','thinking','speaking','success','typing','error'):
    image=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(root/'artifacts/mascot-sources'/f'utterling-{name}.png')))
    layer=image.get_layers()[0]
    layer.add_alpha()
    Gimp.context_push()
    Gimp.context_set_antialias(True)
    Gimp.context_set_sample_threshold(0.15)
    image.select_contiguous_color(Gimp.ChannelOps.REPLACE, layer, 0, 0)
    Gimp.Selection.grow(image, 3)
    f=Gimp.DrawableFilter.new(layer,'gegl:color-to-alpha','Remove exterior white matte')
    c=f.get_config()
    c.set_property('color',Gegl.Color.new('white'))
    c.set_property('transparency-threshold',0.06)
    f.update()
    layer.merge_filter(f)
    Gimp.Selection.none(image)
    Gimp.context_pop()
    proc=Gimp.get_pdb().lookup_procedure('file-png-export')
    config=proc.create_config()
    config.set_property('run-mode',Gimp.RunMode.NONINTERACTIVE)
    config.set_property('image',image)
    config.set_property('file',Gio.File.new_for_path(str(root/'docs/assets/brand'/f'utterling-{name}.png')))
    config.set_property('compression',9)
    config.set_property('bkgd',False)
    result=proc.run(config)
    assert result.index(0)==Gimp.PDBStatusType.SUCCESS, str(result.index(0))
    image.delete()
    print('Exported RGBA:', name)
