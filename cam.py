
import atexit
import cPickle as pickle
import errno
import fnmatch
import io
import os
import picamera
import pygame
import stat
import threading
import time
import yuv2rgb
from pygame.locals import *
from subprocess import call  


class Icon:

	def __init__(self, name):
	  self.name = name
	  try:
	    self.bitmap = pygame.image.load(iconPath + '/' + name + '.png')
	  except:
	    pass


# UI callbacks -------------------------------------------------------------


def isoCallback(n): # Pass 1 (next ISO) or -1 (prev ISO)
	global isoMode
	setIsoMode((isoMode + n) % len(isoData))

def settingCallback(n): # Pass 1 (next setting) or -1 (prev setting)
	global screenMode
	screenMode += n
	if screenMode < 4:               screenMode = len(buttons) - 1
	elif screenMode >= len(buttons): screenMode = 4

def fxCallback(n): # Pass 1 (next effect) or -1 (prev effect)
	global fxMode
	setFxMode((fxMode + n) % len(fxData))

def quitCallback(): # Quit confirmation button
	saveSettings()
	raise SystemExit

def viewCallback(n): # Viewfinder buttons
	global loadIdx, scaled, screenMode, screenModePrior, settingMode, storeMode

	if n is 0:   # Gear icon (settings)
	  screenMode = settingMode # Switch to last settings mode
	elif n is 1: # Play icon (image playback)
	  if scaled: # Last photo is already memory-resident
	    loadIdx         = saveIdx
	    screenMode      =  0 # Image playback
	    screenModePrior = -1 # Force screen refresh
	  else:      # Load image
	    r = imgRange(pathData[storeMode])
	    if r: showImage(r[1]) # Show last image in directory
	    else: screenMode = 2  # No images
	else: # Rest of screen = shutter
	  takePicture()

def doneCallback(): # Exit settings
	global screenMode, settingMode
	if screenMode > 3:
	  settingMode = screenMode
	  saveSettings()
	screenMode = 3 # Switch back to viewfinder mode

def imageCallback(n): # Pass 1 (next image), -1 (prev image) or 0 (delete)
	global screenMode
	if n is 0:
	  screenMode = 1 # Delete confirmation
	else:
	  showNextImage(n)

def deleteCallback(n): # Delete confirmation
	global loadIdx, scaled, screenMode, storeMode
	screenMode      =  0
	screenModePrior = -1
	if n is True:
	  os.remove(pathData[storeMode] + '/IMG_' + '%04d' % loadIdx + '.JPG')
	  os.remove(pathData[storeMode] + '/IMG_' + '%04d' % loadIdx + '.JPG_tb')
	  if(imgRange(pathData[storeMode])):
	    screen.fill(0)
	    pygame.display.update()
	    showNextImage(-1)
	  else: # Last image deleteted; go to 'no images' mode
	    screenMode = 2
	    scaled     = None
	    loadIdx    = -1

def storeModeCallback(n): # Radio buttons on storage settings screen
	global storeMode
	buttons[4][storeMode + 3].setBg('radio3-0')
	storeMode = n
	buttons[4][storeMode + 3].setBg('radio3-1')

def sizeModeCallback(n): # Radio buttons on size settings screen
	global sizeMode
	buttons[5][sizeMode + 3].setBg('radio3-0')
	sizeMode = n
	buttons[5][sizeMode + 3].setBg('radio3-1')
	camera.resolution = sizeData[sizeMode][1]
#	camera.crop       = sizeData[sizeMode][2]


# Global stuff -------------------------------------------------------------

screenMode      =  3      # Current screen mode; default = viewfinder
screenModePrior = -1      # Prior screen mode (for detecting changes)
settingMode     =  4      # Last-used settings mode (default = storage)
storeMode       =  0      # Storage mode; default = Photos folder
storeModePrior  = -1      # Prior storage mode (for detecting changes)
sizeMode        =  0      # Image size; default = Large
fxMode          =  0      # Image effect; default = Normal
isoMode         =  0      # ISO settingl default = Auto
iconPath        = 'icons' # Subdirectory containing UI bitmaps (PNG format)
saveIdx         = -1      # Image index for saving (-1 = none set yet)
loadIdx         = -1      # Image index for loading
scaled          = None    # pygame Surface w/last-loaded image


sizeData = [ # Camera parameters for different size settings
 # Full res      Viewfinder  Crop window
 [(2592, 1944), (320, 240), (0.0   , 0.0   , 1.0   , 1.0   )], # Large
 [(1920, 1080), (320, 180), (0.1296, 0.2222, 0.7408, 0.5556)], # Med
 [(1440, 1080), (320, 240), (0.2222, 0.2222, 0.5556, 0.5556)]] # Small

isoData = [ # Values for ISO settings [ISO value, indicator X position]
 [  0,  27], [100,  64], [200,  97], [320, 137],
 [400, 164], [500, 197], [640, 244], [800, 297]]

fxData = [
  'none', 'sketch', 'gpen', 'pastel', 'watercolor', 'oilpaint', 'hatch',
  'negative', 'colorswap', 'posterise', 'denoise', 'blur', 'film',
  'washedout', 'emboss', 'cartoon', 'solarize' ]

pathData = [
  '/home/pi/Photos',     # Path for storeMode = 0 (Photos folder)
  '/boot/DCIM/CANON999', # Path for storeMode = 1 (Boot partition)
  '/home/pi/Photos']     # Path for storeMode = 2 (Dropbox)

icons = [] # This list gets populated at startup



# Assorted utility functions -----------------------------------------------

def setFxMode(n):
	global fxMode
	fxMode = n
	camera.image_effect = fxData[fxMode]
	buttons[6][5].setBg('fx-' + fxData[fxMode])

def setIsoMode(n):
	global isoMode
	isoMode    = n
	camera.ISO = isoData[isoMode][0]
	buttons[7][5].setBg('iso-' + str(isoData[isoMode][0]))
	buttons[7][7].rect = ((isoData[isoMode][1] - 10,) +
	  buttons[7][7].rect[1:])

def saveSettings():
	try:
	  outfile = open('cam.pkl', 'wb')
	  # Use a dictionary (rather than pickling 'raw' values) so
	  # the number & order of things can change without breaking.
	  d = { 'fx'    : fxMode,
	        'iso'   : isoMode,
	        'size'  : sizeMode,
	        'store' : storeMode }
	  pickle.dump(d, outfile)
	  outfile.close()
	except:
	  pass

def loadSettings():
	try:
	  infile = open('cam.pkl', 'rb')
	  d      = pickle.load(infile)
	  infile.close()
	  if 'fx'    in d: setFxMode(   d['fx'])
	  if 'iso'   in d: setIsoMode(  d['iso'])
	  if 'size'  in d: sizeModeCallback( d['size'])
	  if 'store' in d: storeModeCallback(d['store'])
	except:
	  pass

# Scan files in a directory, locating JPEGs with names matching the
# software's convention (IMG_XXXX.JPG), returning a tuple with the
# lowest and highest indices (or None if no matching files).
def imgRange(path):
	min = 9999
	max = 0
	try:
	  for file in os.listdir(path):
	    if fnmatch.fnmatch(file, 'IMG_[0-9][0-9][0-9][0-9].JPG'):
	      i = int(file[4:8])
	      if(i < min): min = i
	      if(i > max): max = i
	finally:
	  return None if min > max else (min, max)

# Busy indicator.  To use, run in separate thread, set global 'busy'
# to False when done.
def spinner():
	global busy, screenMode, screenModePrior

	pygame.display.update()

	busy = True
	n    = 0
	while busy is True:
	  pygame.display.update()
	  n = (n + 1) % 5

	screenModePrior = -1 # Force refresh

def takePicture():
	global busy, gid, loadIdx, saveIdx, scaled, sizeMode, storeMode, storeModePrior, uid

	# If this is the first time accessing this directory,
	# scan for the max image index, start at next pos.
	#if storeMode != storeModePrior:
	#  r = imgRange(pathData[storeMode])
	#  if r is None:
	#    saveIdx = 1
	#  else:
	#    saveIdx = r[1] + 1
	#    if saveIdx > 9999: saveIdx = 0
	#  storeModePrior = storeMode

	# Scan for next available image slot
	#while True:
	#  filename = pathData[storeMode] + '/IMG_' + '%04d' % saveIdx + '.JPG_tb'
	#  if not os.path.isfile(filename): break
	#  saveIdx += 1
	#  if saveIdx > 9999: saveIdx = 0

	#t = threading.Thread(target=spinner)
	#t.start()

	scaled = None
	camera.resolution = sizeData[sizeMode][0]
	camera.crop       = sizeData[sizeMode][2]
	try:
	  drawText("Taking Image: High Res", 1, 1)
	  camera.capture(filename, use_video_port=False, format='jpeg', thumbnail=None)
	  pygame.display.update()
	  #image = camera.get_image()
	  #window = pygame.display.set_mode((320,240),0)
	  #pygame.image.save(window,'abc.jpg')
	  #drawText("Taking Image: Low Res", 1, 20)
	  camera.resolution = (320, 240)
	  camera.capture(filename + '_tb', use_video_port=False, format='jpeg', thumbnail=None)



	  scaled = pygame.transform.scale(img, sizeData[sizeMode][1])

	finally:
	  # Add error handling/indicator (disk full, etc.)
	  camera.resolution = sizeData[sizeMode][1]
	  camera.crop       = (0.0, 0.0, 1.0, 1.0)

	busy = False
	#t.join()

	if scaled:
	  if scaled.get_height() < 240: # Letterbox
	    screen.fill(0)
	  screen.blit(scaled,
	    ((320 - scaled.get_width() ) / 2,
	     (240 - scaled.get_height()) / 2))
	  pygame.display.update()
	  loadIdx = saveIdx

def showNextImage(direction):
	global busy, loadIdx

	t = threading.Thread(target=spinner)
	t.start()

	n = loadIdx
	while True:
	  n += direction
	  if(n > 9999): n = 0
	  elif(n < 0):  n = 9999
	  if os.path.exists(pathData[storeMode]+'/IMG_'+'%04d'%n+'.JPG_tb'):
	    showImage(n)
	    break

	busy = False
	t.join()

def showImage(n):
	global busy, loadIdx, scaled, screenMode, screenModePrior, sizeMode, storeMode

	t = threading.Thread(target=spinner)
	t.start()

	img      = pygame.image.load(
	            pathData[storeMode] + '/IMG_' + '%04d' % n + '.JPG_tb')
	scaled   = pygame.transform.scale(img, sizeData[sizeMode][1])
	loadIdx  = n

	busy = False
	t.join()

	screenMode      =  0 # Photo playback
	screenModePrior = -1 # Force screen refresh

def drawText(text, xpos, ypos):
  #bitstreamverasans
  #monospace
  myfont = pygame.font.SysFont("bitstreamverasans", 15)
  label = myfont.render(text, 1, (255,255,255))
  screen.blit(label, (xpos, ypos))


# Initialization -----------------------------------------------------------

# Init framebuffer/touchscreen environment variables
os.putenv('SDL_VIDEODRIVER', 'fbcon')
os.putenv('SDL_FBDEV'      , '/dev/fb1')
os.putenv('SDL_MOUSEDRV'   , 'TSLIB')
os.putenv('SDL_MOUSEDEV'   , '/dev/input/touchscreen')

# Get user & group IDs for file & folder creation
# (Want these to be 'pi' or other user, not root)
s = os.getenv("SUDO_UID")
uid = int(s) if s else os.getuid()
s = os.getenv("SUDO_GID")
gid = int(s) if s else os.getgid()

# Buffers for viewfinder data
rgb = bytearray(320 * 240 * 3)
yuv = bytearray(320 * 240 * 3 / 2)

# Init pygame and screen
pygame.init()
pygame.mouse.set_visible(False)
screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)

# Init camera and set up default values
camera            = picamera.PiCamera()
atexit.register(camera.close)
camera.resolution = sizeData[sizeMode][1]
#camera.crop       = sizeData[sizeMode][2]
camera.crop       = (0.0, 0.0, 1.0, 1.0)
# Leave raw format at default YUV, don't touch, don't set to RGB!



loadSettings() # Must come last; fiddles with Button/Icon states


# Main loop ----------------------------------------------------------------

while(True):
  # Process touchscreen input
  while True:
    for event in pygame.event.get():
      if(event.type is MOUSEBUTTONDOWN):
        pos = pygame.mouse.get_pos()
        drawText(str(pos), 1, 220)
        takePicture()
        #break

    if screenMode >= 3 or screenMode != screenModePrior: break

  # Refresh display
  if screenMode >= 3: # Viewfinder or settings modes
    stream = io.BytesIO() # Capture into in-memory stream
    camera.capture(stream, use_video_port=True, format='raw')
    stream.seek(0)
    stream.readinto(yuv)  # stream -> YUV buffer
    stream.close()
    yuv2rgb.convert(yuv, rgb, sizeData[sizeMode][1][0],
      sizeData[sizeMode][1][1])
    img = pygame.image.frombuffer(rgb[0:
      (sizeData[sizeMode][1][0] * sizeData[sizeMode][1][1] * 3)],
      sizeData[sizeMode][1], 'RGB')
  elif screenMode < 2: # Playback mode or delete confirmation
    img = scaled       # Show last-loaded image
  else:                # 'No Photos' mode
    img = None         # You get nothing, good day sir

  if img is None or img.get_height() < 240: # Letterbox, clear background
    screen.fill(0)
  if img:
    screen.blit(img,
      ((320 - img.get_width() ) / 2,
       (240 - img.get_height()) / 2))


  pygame.display.update()

  screenModePrior = screenMode
  
