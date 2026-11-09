"""Export a static PDF with explicit video posters; keep movies in the original PPTX."""
import argparse,json,os,subprocess,tempfile
from pathlib import Path
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=Path('docs/presentation'));a=p.parse_args();out=a.directory.resolve()
prs=Presentation(out/'vision_guided_manipulation.pptx');slides=json.loads((out/'slides.json').read_text())
for slide,note in zip(prs.slides,slides):
 if 'video' not in note:continue
 poster=out.parents[1]/note['video_poster']
 for shape in list(slide.shapes):
  if shape.shape_type==MSO_SHAPE_TYPE.MEDIA:
   left,top,width,height=shape.left,shape.top,shape.width,shape.height;shape._element.getparent().remove(shape._element)
   slide.shapes.add_picture(str(poster),left,top,width=width,height=height)
with tempfile.TemporaryDirectory(prefix='ma6216-static-pdf-') as td:
 tmp=Path(td);source=tmp/'vision_guided_manipulation.pptx';prs.save(source)
 env=dict(os.environ,GSETTINGS_BACKEND='memory',SAL_USE_VCLPLUGIN='svp')
 subprocess.run(['libreoffice','-env:UserInstallation='+ (tmp/'lo-profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(out),str(source)],env=env,check=True)
print('Exported static poster PDF; original PPTX retains embedded videos.')
