"""Append a frame-synchronized active task strip to the complete original replay."""
import hashlib,json,math,subprocess
SPEED=5.0
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/presentation/media'
timeline=json.loads((OUT/'full_task_timeline.json').read_text());source=ROOT/timeline['source'];target=OUT/'complete_task_with_timeline.mp4'
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
filters=[f'setpts=(PTS-STARTPTS)/{SPEED}', 'fps=25', 'pad=1920:860:0:0:color=white', f"drawtext=fontfile={bold}:text='5x playback | continuous sequence':x=20:y=78:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=8"]
for i,c in enumerate(timeline['chapters']):
 x=20+i*380;enabled=f"gte(t,{c['start']/SPEED})*lt(t,{c['end']/SPEED})";sec=int(c['start']/SPEED);stamp=f'{sec//60:02}\\:{sec%60:02}'
 filters.append(f'drawbox=x={x}:y=742:w=360:h=96:color=0xEDF3F5:t=fill')
 for color,enable in [('0x243746',''),('white',f":enable='{enabled}'")]:
  if enable:
   filters.append(f"drawbox=x={x}:y=742:w=360:h=96:color=0x146B8C:t=fill:enable='{enabled}'")
   filters.append(f"drawbox=x={x}:y=742:w=360:h=5:color=0xE5A43B:t=fill:enable='{enabled}'")
  filters.append(f"drawtext=fontfile={font}:text='{stamp}':x={x+14}:y=758:fontsize=25:fontcolor={color}"+enable)
  filters.append(f"drawtext=fontfile={bold}:text='{c['title']}':x={x+14}:y=796:fontsize=25:fontcolor={color}"+enable)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),'-map','0:v:0','-an','-vf',','.join(filters),'-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-vsync','0','-movflags','+faststart',str(target)],check=True)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(target),'-frames:v','1',str(OUT/'full_task_timeline_poster.jpg')],check=True)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=duration,nb_frames','-of','json',str(target)]))['streams'][0]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'source':str(source.relative_to(ROOT)),'source_sha256':sha(source),'timeline_source':'docs/presentation/media/full_task_timeline.json','timeline_sha256':sha(OUT/'full_task_timeline.json'),'output':str(target.relative_to(ROOT)),'output_sha256':sha(target),'duration_s':float(probe['duration']),'playback_speed':SPEED,'fps':25,'frame_count':int(probe['nb_frames']),'dimensions':[1920,860],'transformation':'Append 140-pixel task strip; preserve original 1920x720 viewport and complete chronological sequence; play at 5x speed and resample to 25 fps. Chapter timestamps use presentation time; original replay is retained separately.','chapters':[dict(c,start=c['start']/SPEED,end=c['end']/SPEED,first_active_frame=math.ceil(c['start']/SPEED*25)) for c in timeline['chapters']]}
(OUT/'full_task_timeline_video.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Complete video with synchronized task highlighting exported.',flush=True)
