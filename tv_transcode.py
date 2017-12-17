#! /usr/bin/env python

import os, os.path, sys, shutil
import getpass, subprocess
from xml.etree import ElementTree
import urllib2
import logging
import datetime
import json
from pprint import pprint

params = {}
plex_token = 'sXSzKgwKQNU9Q2CFyWcY'
plex_server = 'localhost'
plex_port = '32400'
default_tv_directory = '/Volumes/Public/media/TV/TV-14'
tv_root = '/Volumes/Public/media/TV'
originals_directory = '/Users/james/Movies/original-dvr-files/%s' % (datetime.date.today())
comskip_directory='/Users/james/bin/comskip'


# set up logging
log_file_name = '/Users/james/bin/tv_transcode.log'
log_file_directory = '/Users/james/bin/logs'
original_files_directory="/Users/james/Movies/original-dvr-files"
transcoded_directory='/Users/james/Movies/transcoded'

logger = logging.getLogger('tv_transcode')
hdlr = logging.FileHandler(log_file_name)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.DEBUG)


html_escape_table = {
  "&": "&amp;",
  '"': "&quot;",
  "'": "&apos;",
  ">": "&gt;",
  "<": "&lt;",
  ' ': "+",
}
ffmpeg_args = {
  'ab': 128, # audio bitrate is 128kbps by default
  'vb': 800, # video bitrate is 800K by default
}

def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

def html_escape(text):
  """Produce entities within text."""
  return "".join(html_escape_table.get(c,c) for c in text)

def get_show_directory(show_name):
  show_name = show_name.strip()
  url = 'http://%s:%s/hubs/search?query=%s&X-Plex-Token=%s' % (plex_server, plex_port, html_escape(show_name), plex_token)
  try:
    xml_text = urllib2.urlopen(url).read()
    tree = ElementTree.fromstring(xml_text)
    for hub in tree.findall('Hub'):
      type = hub.attrib.get('type')

      if type == 'show':
        for directory in hub.findall('Directory'):
          title = directory.attrib.get('title')

          if show_name in title:
            for location in directory.findall('Location'):
              path = location.attrib.get('path')
              if tv_root in path:
                return path
          pass
  except (urllib2.URLError):
    # if we couldn't connect we just continue and use the default directory
    pass
  # nothing was found, so use the default
  # create a new directory in the tv_default
  path = '%s/%s' % (default_tv_directory, sanitize_file_name(show_name))
  if not os.path.exists(path):
    os.makedirs(path)
  return path
  pass

def sanitize_file_name(name):
  name = name.replace(' - ', '.')
  name = name.replace("'", '')
  name = name.replace(' ', '-')
  name = name.replace(';', '--')
  return name

def run_comskip(file_name):
  # look for comskip config file
  # check to see if there is a comskip.ini in the file's directory, if not copy the found config
  file_dir = os.path.dirname(file_name)
  if file_dir == '':
    file_dir = os.curdir;
  print "file_dir: %s" % (file_dir)
  comskip_config = '%s/comskip.ini' % comskip_directory
  comskip_ini_file = '%s/comskip.ini' % file_dir
  if not os.path.isfile(comskip_ini_file):
    series_name = file_name.split('.')[0]
    possible_comskip_config = '%s/%s.ini' % (comskip_directory, series_name)
    print "possible_conskip_config: %s" % (possible_comskip_config)
    if os.path.isfile(possible_comskip_config):
      comskip_config = possible_comskip_config

    series_name = file_name.split(' - ')[0]
    possible_comskip_config = '%s/%s.ini' % (comskip_directory, series_name)
    print "possible_conskip_config: %s" % (possible_comskip_config)
    if os.path.isfile(possible_comskip_config):
      comskip_config = possible_comskip_config

    #print "copying file %s to %s" % (comskip_config, comskip_ini_file)
    #shutil.copyfile(comskip_config, comskip_ini_file)

  os.chdir(file_dir)
  #comskip_command = 'comskip --csvout -t -n  "%s"' % (file_name)
  comskip_command = 'comskip --ini=%s -n "%s"' % (comskip_config, file_name)
  print "comskip_command: %s" % comskip_command
  print "running comskip..."
  os.system(comskip_command)

  # cut the file
  edl_file = '.'.join(file_name.split('.')[0:-1]) + '.edl'
  print 'edl_file: "%s"' % edl_file
  with open(edl_file) as f:
    start = 0;
    end = 0;
    part = 1;
    parts = []
    for l in f:
      array = l.strip().split("\t")
      print array
      end = float(array[0])
      part_name = '.'.join(file_name.split('.')[0:-1]) + ('-part_%s.ts' % (part))
      length = end - start;
      command = '/usr/local/bin/ffmpeg -ss %s -i "%s" -t %s -y -acodec copy -vcodec copy -scodec copy "%s"' % (start, file_name, end, part_name)
      print 'command: %s' % command
      os.system(command)

      start = float(array[1])
      part = part + 1
      parts.append(part_name)
    # do the last segment
    part_name = '.'.join(file_name.split('.')[0:-1]) + ('-part_%s.ts' % (part))
    command = '/usr/local/bin/ffmpeg -ss %s -i "%s" -y -acodec copy -vcodec copy -scodec copy "%s"' % (start, file_name, part_name)
    print 'command: %s' % command
    os.system(command)
    parts.append(part_name)
    print 'parts: %s' % (parts)

    # move opriginal
    original_new_location = '%s/%s' % (originals_directory, file_name.split('/')[-1])
    ensure_dir(original_new_location)
    mv_command = 'mv "%s" "%s"' % (file_name, original_new_location)
    os.system(mv_command)

    # concatenate them
    comskipped_file = '.'.join(file_name.split('.')[0:-1]) + '-comskipped.ts'
    command = '/usr/local/bin/ffmpeg -i "concat:%s" -y -acodec copy -vcodec copy "%s"' % ('|'.join(parts), comskipped_file)
    print 'command: %s' % command
    os.system(command)

    # delete parts
    for f in parts:
      os.remove(f)

    return comskipped_file


def process_file(original_file_name):
  moved = False;
  #file_name = run_comskip(original_file_name)
  #if file_name:
  #  moved = True
  #  original_file_name = file_name

  probe_command = '/usr/local/bin/ffprobe -v quiet  -print_format json -show_format -show_streams "%s" > "%s.json"' %  (original_file_name, original_file_name)
  logger.info('probe_command: %s' % probe_command)
  #print 'probe_command: %s' % probe_command
  os.system(probe_command)
  video_frame_rate = False
  audio_sample_rate = False
  
  with open('%s.json' % original_file_name) as json_data:
    d = json.load(json_data)
    #logger.info('json_data: %s' % json_data)
    #print "json data: %s" % (d)
    for stream in d['streams']:
      #print ''
      #print ''
      #print '------------------------------ stream -----------------------------'
      #pprint(stream)
      if stream['codec_type'] == 'video':
        video_frame_rate = float(stream['avg_frame_rate'].split('/')[0]) / float(stream['avg_frame_rate'].split('/')[1])
        # check to see if it is an integer, if not truncate at the hundredths
        if video_frame_rate - int(video_frame_rate) != 0:
          video_frame_rate = int(video_frame_rate * 100)/100.00
        else:
          video_frame_rate = int(video_frame_rate)
      elif stream['codec_type'] == 'audio':
        audio_sample_rate = float(stream['sample_rate'])/1000
        if audio_sample_rate - int(audio_sample_rate) != 0:
          audio_sample_rate = int(audio_sample_rate * 100)/100.00
        else:
          audio_sample_rate = int(audio_sample_rate)

  print 'video_frame_rate: %s' % (video_frame_rate)
  logger.info('video_frame_rate: %s' % video_frame_rate)
  print 'audio_sample_rate: %s' % (audio_sample_rate)
  logger.info('audio_sample_rate: %s' % audio_sample_rate)
    #print(d)


  logger.info('original_file_name: "%s"' % original_file_name)
  file_name = '.'.join(original_file_name.split('/')[-1].split('.')[:-1]) + '.mp4'
  logger.info('file_name: "%s"' % file_name)
  
  show_name = file_name.split('.')[0].split(' - ')[0].split('(')[0]
  show_directory = get_show_directory(show_name)
  original_new_location = '%s/%s' % (originals_directory, original_file_name.split('/')[-1])
  transcoded_file_name = '%s/%s' % (show_directory, sanitize_file_name(file_name))
  logger.info('transcoded_file_name: "%s"' % transcoded_file_name)
  # move the original file
  #os.rename(original_file_name, original_file_new_location)

  #
  # This sets up logging for this transcode transaction
  #
  #log_file_name = file_name = '.'.join(original_file_name.split('/')[-1].split('.')[:-1]) + '.log'
  #log_file_full_path = '%s/%s' % (log_file_directory, sanitize_file_name(log_file_name))
  #os.system('touch "%s"' % (log_file_full_path))
  #os.system('chmod 777 "%s"' % (log_file_full_path))
  #os.environ['FFREPORT'] = 'log_level=32:file=%s' % (log_file_full_path)
  #transcode the video
  command = '/usr/local/bin/ffmpeg -i "%s"  -acodec aac -strict -2 -ab 128k -ar 44100 -vcodec h264 -vb 800K -y -movflags +faststart "%s"' % (original_file_name, transcoded_file_name)
  command = '/usr/bin/nice -n 10 /usr/local/bin/ffmpeg -i "%s"  -acodec aac -ac 2 -strict -2 -ab 128k -ar 44100 -vcodec copy -y -movflags +faststart "%s"' % (original_file_name, transcoded_file_name)
  command = '/usr/bin/nice -n 10 /usr/local/bin/ffmpeg -i "%s"  -acodec aac -ac 2 -strict -2 -ab 128k -af "aresample=matrix_encoding=dplii" -ar 44100 -vcodec copy -y -movflags +faststart "%s"' % (original_file_name, transcoded_file_name)
  #command = '/usr/bin/nice -n 10  /usr/local/bin/HandBrakeCLI -e x264  -a 1,1 -E ffaac,copy:ac3 -B 96,96 -6 dpl2,none -R Auto,Auto -D 0.0,0.0 --audio-copy-mask aac,ac3,dtshd,dts,mp3 --mixdown stereo,5point1 --audio-fallback ffac3 -f mp4 --decomb --loose-anamorphic --modulus 2 -m --x264-preset medium --h264-profile main --h264-level 3.1 -O -b 600 --two-pass --turbo %s -i "%s" -o "%s"' % (sub_file_args, orig_file_name, new_file_name)
  #command = '/usr/local/bin/HandBrakeCLI -e x264  -a 1,1 -E ffaac,copy:ac3 -B 96,160 -R Auto,Auto -D 0.0,0.0 --gain 5.0 --audio-copy-mask aac,ac3,dtshd,dts,mp3 --mixdown stereo,none --audio-fallback ffac3 -f mp4 --decomb --loose-anamorphic --modulus 2 -m --x264-preset medium --h264-profile main --h264-level 3.1 -O -b 800 --two-pass --turbo -i "%s" -o "%s"'  % (original_file_name, transcoded_file_name)
  #command = '/usr/bin/nice -n 10 /usr/local/bin/HandBrakeCLI -e x264  -a 1,1 -E ffaac,copy:ac3 -B 80,160 -R Auto,Auto -D 0.0,0.0 --gain 5.0 --audio-copy-mask aac,ac3,dtshd,dts,mp3 --mixdown stereo,none --audio-fallback ffac3 -f mp4 --decomb --loose-anamorphic --modulus 2 -m --x264-preset medium --h264-profile main --h264-level 3.1 -O -q 20 --two-pass --turbo -i "%s" -o "%s"'  % (original_file_name, transcoded_file_name)
  #command = '/usr/bin/nice -n 10 /usr/local/bin/HandBrakeCLI  --encoder-preset slow --encoder-level 3.1 --colormatrix 709 --deblock  -O -i "%s" -o "%s"'  % (original_file_name, transcoded_file_name)

  command = '/usr/bin/nice -n 10 /usr/local/bin/ffmpeg -i "%s" -o "%s"' % (original_file_name, transcoded_file_name)


  command = '/usr/bin/nice -n 10 /usr/local/bin/ffmpeg -i "%s" -c:v libx264 -crf 24 -level 3.1 -preset slow -tune film -filter:v scale=-1:720 -sws_flags lanczos -c:a aac -q:a 100 -y "%s"' % (original_file_name, transcoded_file_name)

  command = '/usr/bin/nice -n 10 /usr/local/bin/HandBrakeCLI --preset "Android Tablet" -s "0,1,2,3,4,5,6" -O -i "%s" -o "%s"' % (original_file_name, transcoded_file_name)


  # attempting to use SD.TV.x264.Releasing.Standards.2016
  command  = '/usr/bin/nice -n 10 /usr/local/bin/HandBrakeCLI '
  command += '--encoder x264 '        # 4.1
  command += '--quality 22.0 '        # 4.4 quality of 19-24
  command += '--encoder-preset slow ' # 4.6
  command += '--encoder-level 5.1 '   # 4.7
  command += '--color-matrix 709 '    # 4.8
  command += '--encoder-tune film '   # 4.17
  command += '-x '
  command += 'deblock=2,2:'           # 4.11
  command += 'keyint=300:'            # 4.12
  command += 'min-keyint=60:'         # 4.13
  #command += 'threads=2 '
  command += '--modulus 2 '           # 5.1
  command += '--cfr '                 # 7.1
  command += '--aq 2 '                # 8.2.1
  command += '--normalize-mix 1 '     # 8.2.3
  command += '--mixdown dpl2 '        # 8.2.5

  if video_frame_rate and audio_sample_rate:
    command += '-r %s ' % (video_frame_rate)
    command += '-arate %s ' % (audio_sample_rate)

  #command += bitrate=5200:vbv-bufsize=5200:vbv-maxrate=5200:level=42:bframes=2::ref=4:me=umh:merange=64:subme=7:8x8dct:cabac=1 '
  command += '-O -i "%s" -o "%s"' % (original_file_name, transcoded_file_name)

  #command = '/usr/bin/nice -n 10 /usr/local/bin/HandBrakeCLI --preset "Universal" -q 24.0 -s "0,1,2,3,4,5,6" -O -i "%s" -o "%s"' % (original_file_name, transcoded_file_name)
  #command_list = [command]
  #command_list = [
  #  'ffmpeg',
  #  '-i "%s"' % (original_file_name),
  #  '-acodec aac',
  #  '-strict',
  #   '-2',
  #   '-ab 128k',
  #   '-ar 44100',
  #   '-vcodec h264',
  #   '-vb 800K',
  #   '-y',
  #   '-movflags',
  #   '+faststart',
  #   transcoded_file_name,
  # ]
  logger.info("command: '%s'" % command)
  print "command: %s" % command
  result = os.system(command)
  #output = subprocess.check_output(command_list)
  logger.info("ffmpeg command completed with exit code: %s'" % result)
  if result == 0 and not moved:
    # the transcode/remux was successful so move the original so plex cannot
    # place it in the final location, we have already placed the transcoded file
    # there
    logger.info("moving original file '%s' to '%s'" % (original_file_name, original_new_location))
    # make sure the destination directory exists
    ensure_dir(original_new_location)
    #os.rename(original_file_name, original_new_location)
    # we use the mv command in the system since python os.rename cannot move
    # across file systems
    #mv_command = 'mv "%s" "%s"' % (original_file_name, original_new_location)
    #os.system(mv_command)

if __name__ == "__main__":
  logger.info('sys.argv: "%s"' % sys.argv)
  #original_file_name = sys.argv[1];
  
  args = sys.argv[1:]
  files_to_convert = []
  for arg in args:
    if ('--' in arg):
      param_name = arg.split('--')[1].split('=')[0]
      if (param_name == 'help'):
        output_help()
        exit()
      if (len(arg.split('=')) > 1):
        param = arg.split('=')[1]
      else:
        param = 1

      params[param_name] = param

    elif (arg[0] == '-'):
      # this is an argument not a file to convert

      ffmpeg_args[arg.split('-')[1].split('=')[0]] = arg.split('=')[1]
    elif (os.path.isfile(arg)) :
      # we have confirmed that the argument is a file

      files_to_convert.append(arg)
  #print "ffmpeg_args: %s" % ffmpeg_args

  if ('test-replace' in params.keys()):
    simulate_file_name_replace(files_to_convert)
    exit(0)

  logger.info('files_to_convert: %s' % files_to_convert)
  for file_to_convert in files_to_convert:
    print 'process_file(%s)' % file_to_convert
    logger.info('process_file(%s)' % file_to_convert)
    process_file(file_to_convert)


