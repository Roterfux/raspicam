import os
import io
import fnmatch
import pickle
import threading
import pygame
from pygame.locals import *
from picamera import PiCamera


class CameraApp:
    def __init__(self):
        # --- State ---
        self.screen_mode = 3
        self.screen_mode_prior = -1
        self.setting_mode = 4

        self.store_mode = 0
        self.size_mode = 0
        self.fx_mode = 0
        self.iso_mode = 0

        self.save_idx = -1
        self.load_idx = -1
        self.scaled = None
        self.busy = False

        # --- Data ---
        self.size_data = [
            [(2592, 1944), (320, 240), (0.0, 0.0, 1.0, 1.0)],
            [(1920, 1080), (320, 180), (0.1296, 0.2222, 0.7408, 0.5556)],
            [(1440, 1080), (320, 240), (0.2222, 0.2222, 0.5556, 0.5556)]
        ]

        self.iso_data = [
            [0, 27], [100, 64], [200, 97], [320, 137],
            [400, 164], [500, 197], [640, 244], [800, 297]
        ]

        self.fx_data = [
            'none', 'sketch', 'gpen', 'pastel', 'watercolor', 'oilpaint',
            'hatch', 'negative', 'colorswap', 'posterise', 'denoise',
            'blur', 'film', 'washedout', 'emboss', 'cartoon', 'solarize'
        ]

        self.path_data = [
            '/home/pi/Photos',
            '/boot/DCIM/CANON999',
            '/home/pi/Photos'
        ]

        # --- Init ---
        self.init_pygame()
        self.init_camera()
        self.font = pygame.font.SysFont("bitstreamverasans", 15)

        self.rgb = bytearray(320 * 240 * 3)
        self.yuv = bytearray(320 * 240 * 3 // 2)

        self.load_settings()

    def init_pygame(self):
        os.putenv('SDL_VIDEODRIVER', 'fbcon')
        os.putenv('SDL_FBDEV', '/dev/fb1')
        os.putenv('SDL_MOUSEDRV', 'TSLIB')
        os.putenv('SDL_MOUSEDEV', '/dev/input/touchscreen')

        pygame.init()
        pygame.mouse.set_visible(False)
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    def init_camera(self):
        self.camera = PiCamera()
        self.camera.resolution = self.size_data[self.size_mode][1]
        self.camera.crop = (0.0, 0.0, 1.0, 1.0)

    # --- Settings ---
    def save_settings(self):
        try:
            with open('cam.pkl', 'wb') as f:
                pickle.dump({
                    'fx': self.fx_mode,
                    'iso': self.iso_mode,
                    'size': self.size_mode,
                    'store': self.store_mode
                }, f)
        except Exception:
            pass

    def load_settings(self):
        try:
            with open('cam.pkl', 'rb') as f:
                d = pickle.load(f)

            self.fx_mode = d.get('fx', 0)
            self.iso_mode = d.get('iso', 0)
            self.size_mode = d.get('size', 0)
            self.store_mode = d.get('store', 0)

        except Exception:
            pass

    # --- Utils ---
    def draw_text(self, text, x, y):
        label = self.font.render(text, True, (255, 255, 255))
        self.screen.blit(label, (x, y))

    def img_range(self, path):
        min_idx, max_idx = 9999, 0
        try:
            for file in os.listdir(path):
                if fnmatch.fnmatch(file, 'IMG_[0-9][0-9][0-9][0-9].JPG'):
                    i = int(file[4:8])
                    min_idx = min(min_idx, i)
                    max_idx = max(max_idx, i)
        except Exception:
            return None

        return None if min_idx > max_idx else (min_idx, max_idx)

    # --- Camera ---
    def take_picture(self):
        filename = os.path.join(
            self.path_data[self.store_mode],
            'IMG_%04d.JPG' % (self.save_idx if self.save_idx >= 0 else 0)
        )

        self.camera.resolution = self.size_data[self.size_mode][0]

        try:
            self.draw_text("Capturing...", 10, 10)
            pygame.display.update()

            self.camera.capture(filename, format='jpeg')
            self.camera.resolution = (320, 240)
            self.camera.capture(filename + '_tb', format='jpeg')

            img = pygame.image.load(filename + '_tb')
            self.scaled = pygame.transform.scale(img, self.size_data[self.size_mode][1])

        finally:
            self.camera.resolution = self.size_data[self.size_mode][1]

    # --- UI Loop ---
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                self.draw_text(str(pos), 1, 220)
                self.take_picture()

    def update_viewfinder(self):
        stream = io.BytesIO()
        self.camera.capture(stream, use_video_port=True, format='raw')
        stream.seek(0)
        stream.readinto(self.yuv)

        # naive grayscale fallback (no yuv2rgb dependency)
        img = pygame.image.frombuffer(
            bytes(self.yuv[:320*240]),
            (320, 240),
            'P'
        )
        return img

    def render(self):
        if self.screen_mode >= 3:
            img = self.update_viewfinder()
        elif self.screen_mode < 2:
            img = self.scaled
        else:
            img = None

        if img is None or img.get_height() < 240:
            self.screen.fill(0)

        if img:
            self.screen.blit(img, (0, 0))

        pygame.display.update()

    def run(self):
        try:
            while True:
                self.handle_events()
                self.render()
        finally:
            self.camera.close()


if __name__ == '__main__':
    app = CameraApp()
    app.run()
