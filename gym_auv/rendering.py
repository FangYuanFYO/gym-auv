"""
2D rendering framework.
Modified version of the classical control module in OpenAI's gym.

Changes:
    - Added an 'origin' argument to the draw_circle() and make_circle() functions to allow drawing of circles anywhere.
    - Added an 'outline' argument to the draw_circle() function, allows a more stylised render

Created by Haakon Robinson, based on OpenAI's gym.base_env.classical.rendering.py
"""

import os
import six
import sys
import pyglet
from pyglet import gl
import numpy as np
import math
from numpy import pi, sin, cos, arctan2
from gym import error

if "Apple" in sys.version:
    if 'DYLD_FALLBACK_LIBRARY_PATH' in os.environ:
        os.environ['DYLD_FALLBACK_LIBRARY_PATH'] += ':/usr/lib'
        # (JDS 2016/04/15): avoid bug on Anaconda 2.3.0 / Yosemite

STATE_W = 96 
STATE_H = 96
VIDEO_W = 720
VIDEO_H = 600
WINDOW_W = 720
WINDOW_H = 600

SCALE       = 5.0        # Track scale
PLAYFIELD   = WINDOW_W# 3000/SCALE # Game over boundary
FPS         = 50
ZOOM        = 3.0          # Camera ZOOM
ZOOM_FOLLOW = True       # Set to False for fixed view (don't use ZOOM)

RAD2DEG = 57.29577951308232

env_bg = None
rot_angle = None

def get_display(spec):
    """Convert a display specification (such as :0) into an actual Display
    object.

    Pyglet only supports multiple Displays on Linux.
    """
    if spec is None:
        return None
    elif isinstance(spec, six.string_types):
        return pyglet.canvas.Display(spec)
    else:
        raise error.Error('Invalid display specification: {}. (Must be a string like :0 or None.)'.format(spec))


class Viewer(object):
    def __init__(self, width, height, display=None):
        display = get_display(display)

        self.width = width
        self.height = height
        self.window = pyglet.window.Window(width=width, height=height, display=display)
        self.window.on_close = self.window_closed_by_user
        self.isopen = True
        self.geoms = []
        self.onetime_geoms = []
        self.fixed_geoms = []
        self.transform = Transform()

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def close(self):
        self.window.close()

    def window_closed_by_user(self):
        self.isopen = False

    def set_bounds(self, left, right, bottom, top):
        assert right > left and top > bottom
        scalex = self.width/(right-left)
        scaley = self.height/(top-bottom)
        self.transform = Transform(
            translation=(-left*scalex, -bottom*scaley),
            scale=(scalex, scaley))

    def add_geom(self, geom):
        self.geoms.append(geom)

    def add_onetime(self, geom):
        self.onetime_geoms.append(geom)

    def add_fixed(self, geom):
        self.fixed_geoms.append(geom)

    def render(self, return_rgb_array=False):
        gl.glClearColor(1, 1, 1, 1)
        self.window.clear()
        self.window.switch_to()
        self.window.dispatch_events()
        self.transform.enable()
        for geom in self.geoms:
            geom.render()
        for geom in self.onetime_geoms:
            geom.render()
        self.transform.disable()
        for geom in self.fixed_geoms:
            geom.render()
        arr = None
        if return_rgb_array:
            buffer = pyglet.image.get_buffer_manager().get_color_buffer()
            image_data = buffer.get_image_data()
            arr = np.fromstring(image_data.data, dtype=np.uint8, sep='')
            # In https://github.com/openai/gym-http-api/issues/2, we
            # discovered that someone using Xmonad on Arch was having
            # a window of size 598 x 398, though a 600 x 400 window
            # was requested. (Guess Xmonad was preserving a pixel for
            # the boundary.) So we use the buffer height/width rather
            # than the requested one.
            arr = arr.reshape(buffer.height, buffer.width, 4)
            arr = arr[::-1,:,0:3]
        self.window.flip()
        self.onetime_geoms = []
        return arr if return_rgb_array else self.isopen

    def draw_circle(self, origin=(0,0), radius=10, res=30, filled=True, outline=True, **attrs):
        geom = make_circle(origin=origin, radius=radius, res=res, filled=filled)
        _add_attrs(geom, attrs)
        self.add_onetime(geom)
        if filled and outline:
            outl = make_circle(origin=origin, radius=radius, res=res, filled=False)
            _add_attrs(outl, {'color': (0,0,0), 'linewidth': 1})
            self.add_onetime(outl)
        return geom

    def draw_polygon(self, v, filled=True, **attrs):
        geom = make_polygon(v=v, filled=filled)
        _add_attrs(geom, attrs)
        self.add_onetime(geom)
        return geom

    def draw_polyline(self, v, **attrs):
        geom = make_polyline(v=v)
        _add_attrs(geom, attrs)

        self.add_onetime(geom)
        return geom

    def draw_line(self, start, end, **attrs):
        geom = Line(start, end)
        _add_attrs(geom, attrs)
        self.add_onetime(geom)
        return geom

    def get_array(self):
        self.window.flip()
        image_data = pyglet.image.get_buffer_manager().get_color_buffer().get_image_data()
        self.window.flip()
        arr = np.fromstring(image_data.data, dtype=np.uint8, sep='')
        arr = arr.reshape(self.height, self.width, 4)
        return arr[::-1,:,0:3]

    def transform_vertices(self, points, translation, rotation, scale=1):
        res = []
        for p in points:
            res.append((
                cos(rotation) * p[0] * scale - sin(rotation) * p[1] * scale + translation[0],
                sin(rotation) * p[0] * scale + cos(rotation) * p[1] * scale + translation[1]))
        return res

    def draw_arrow(self, base, angle, length, **attrs):
        TRIANGLE_POLY = ((-1, -1), (1, -1), (0, 1))
        head = (base[0] + length * cos(angle), base[1] + length * sin(angle))
        tri = self.transform_vertices(TRIANGLE_POLY, head, angle - np.pi / 2, scale=0.7)
        self.draw_polyline([base, head], linewidth=2, **attrs)
        self.draw_polygon(tri, **attrs)

    def draw_shape(self, vertices, position, angle, color):
        poly_path = self.transform_vertices(vertices, position, angle)
        self.draw_polygon(poly_path, color=color)
        self.draw_polyline(poly_path + [poly_path[0]], linewidth=2, color=(0, 0, 0))

    def __del__(self):
        self.close()


def _add_attrs(geom, attrs):
    if "color" in attrs:
        geom.set_color(*attrs["color"])
    if "linewidth" in attrs:
        geom.set_linewidth(attrs["linewidth"])


class Geom(object):
    def __init__(self):
        self._color=Color((0, 0, 0, 1.0))
        self.attrs = [self._color]

    def render(self):
        for attr in reversed(self.attrs):
            attr.enable()
        self.render1()
        for attr in self.attrs:
            attr.disable()

    def render1(self):
        raise NotImplementedError

    def add_attr(self, attr):
        self.attrs.append(attr)

    def set_color(self, r, g, b):
        self._color.vec4 = (r, g, b, 1)


class Attr(object):
    def enable(self):
        raise NotImplementedError

    def disable(self):
        pass


class Transform(Attr):
    def __init__(self, translation=(0.0, 0.0), rotation=0.0, scale=(1,1)):
        self.set_translation(*translation)
        self.set_rotation(rotation)
        self.set_scale(*scale)

    def enable(self):
        gl.glPushMatrix()
        gl.glTranslatef(self.translation[0], self.translation[1], 0) # translate to GL loc ppint
        gl.glRotatef(RAD2DEG * self.rotation, 0, 0, 1.0)
        gl.glScalef(self.scale[0], self.scale[1], 1)

    def disable(self):
        gl.glPopMatrix()

    def set_translation(self, newx, newy):
        self.translation = (float(newx), float(newy))

    def set_rotation(self, new):
        self.rotation = float(new)

    def set_scale(self, newx, newy):
        self.scale = (float(newx), float(newy))


class Color(Attr):
    def __init__(self, vec4):
        self.vec4 = vec4

    def enable(self):
        gl.glColor4f(*self.vec4)


class LineStyle(Attr):
    def __init__(self, style):
        self.style = style

    def enable(self):
        gl.glEnable(gl.GL_LINE_STIPPLE)
        gl.glLineStipple(1, self.style)

    def disable(self):
        gl.glDisable(gl.GL_LINE_STIPPLE)


class LineWidth(Attr):
    def __init__(self, stroke):
        self.stroke = stroke

    def enable(self):
        gl.glLineWidth(self.stroke)


class Point(Geom):
    def __init__(self):
        Geom.__init__(self)

    def render1(self):
        gl.glBegin(gl.GL_POINTS) # draw point
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glEnd()


class FilledPolygon(Geom):
    def __init__(self, v):
        Geom.__init__(self)
        self.v = v

    def render1(self):
        if   len(self.v) == 4 : gl.glBegin(gl.GL_QUADS)
        elif len(self.v)  > 4 : gl.glBegin(gl.GL_POLYGON)
        else: gl.glBegin(gl.GL_TRIANGLES)
        for p in self.v:
            gl.glVertex3f(p[0], p[1],0)  # draw each vertex
        gl.glEnd()


def make_circle(origin=(0,0), radius=10, res=30, filled=True):
    points = []
    for i in range(res):
        ang = 2*math.pi*i / res
        points.append((math.cos(ang)*radius + origin[0], math.sin(ang)*radius + origin[1]))
    if filled:
        return FilledPolygon(points)
    else:
        return PolyLine(points, True)


def make_polygon(v, filled=True):
    if filled: return FilledPolygon(v)
    else: return PolyLine(v, True)


def make_polyline(v):
    return PolyLine(v, False)


def make_capsule(length, width):
    l, r, t, b = 0, length, width/2, -width/2
    box = make_polygon([(l,b), (l,t), (r,t), (r,b)])
    circ0 = make_circle(width/2)
    circ1 = make_circle(width/2)
    circ1.add_attr(Transform(translation=(length, 0)))
    geom = Compound([box, circ0, circ1])
    return geom


class Compound(Geom):
    def __init__(self, gs):
        Geom.__init__(self)
        self.gs = gs
        for g in self.gs:
            g.attrs = [a for a in g.attrs if not isinstance(a, Color)]

    def render1(self):
        for g in self.gs:
            g.render()


class PolyLine(Geom):
    def __init__(self, v, close):
        Geom.__init__(self)
        self.v = v
        self.close = close
        self.linewidth = LineWidth(1)
        self.add_attr(self.linewidth)

    def render1(self):
        gl.glBegin(gl.GL_LINE_LOOP if self.close else gl.GL_LINE_STRIP)
        for p in self.v:
            gl.glVertex3f(p[0], p[1],0)  # draw each vertex
        gl.glEnd()

    def set_linewidth(self, x):
        self.linewidth.stroke = x


class Line(Geom):
    def __init__(self, start=(0.0, 0.0), end=(0.0, 0.0)):
        Geom.__init__(self)
        self.start = start
        self.end = end
        self.linewidth = LineWidth(1)
        self.add_attr(self.linewidth)

    def render1(self):
        gl.glBegin(gl.GL_LINES)
        gl.glVertex2f(*self.start)
        gl.glVertex2f(*self.end)
        gl.glEnd()


class Image(Geom):
    def __init__(self, fname, width, height):
        Geom.__init__(self)
        self.width = width
        self.height = height
        img = pyglet.image.load(fname)
        self.img = img
        self.flip = False

    def render1(self):
        self.img.blit(-self.width/2, -self.height/2, width=self.width, height=self.height)


# ================================================================
class SimpleImageViewer(object):
    def __init__(self, display=None, maxwidth=500):
        self.window = None
        self.isopen = False
        self.display = display
        self.maxwidth = maxwidth

    def imshow(self, arr):
        if self.window is None:
            height, width, _channels = arr.shape
            if width > self.maxwidth:
                scale = self.maxwidth / width
                width = int(scale * width)
                height = int(scale * height)
            self.window = pyglet.window.Window(width=width, height=height, 
                display=self.display, vsync=False, resizable=True)            
            self.width = width
            self.height = height
            self.isopen = True

            @self.window.event
            def on_resize(width, height):
                self.width = width
                self.height = height

            @self.window.event
            def on_close():
                self.isopen = False

        assert len(arr.shape) == 3, "You passed in an image with the wrong number shape"
        image = pyglet.image.ImageData(arr.shape[1], arr.shape[0], 
            'RGB', arr.tobytes(), pitch=arr.shape[1]*-3)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, 
            gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        texture = image.get_texture()
        texture.width = self.width
        texture.height = self.height
        self.window.clear()
        self.window.switch_to()
        self.window.dispatch_events()
        texture.blit(0, 0) # draw
        self.window.flip()

    def close(self):
        if self.isopen:
            self.window.close()
            self.isopen = False

    def __del__(self):
        self.close()


def render_env(env, mode):
    global rot_angle

    def render_objects():
        t.enable()
        _render_path(env)
        _render_progress(env)
        _render_vessel(env)
        _render_tiles(env, win)
        _render_obstacles(env)

        # Visualise path error (DEBUGGING)
        # p = np.array(env.vessel.position)
        # dir = rotate(env.past_obs[-1][0:2], env.vessel.heading)
        # env.viewer.draw_line(p, p + 10*np.array(dir), color=(0.8, 0.3, 0.3))

        for geom in env.viewer.onetime_geoms:
           geom.render()

        t.disable()

        _render_indicators(env, WINDOW_W, WINDOW_H)

    scroll_x = env.vessel.position[0]
    scroll_y = env.vessel.position[1]
    ship_angle = -env.vessel.heading + pi/2
    if (rot_angle is None):
        rot_angle = ship_angle
    else:
        rot_angle += 0.01 * (ship_angle - rot_angle)

    env.viewer.transform.set_scale(ZOOM, ZOOM)
    env.viewer.transform.set_translation(
        WINDOW_W/2 - (scroll_x*ZOOM*cos(rot_angle) - scroll_y*ZOOM*sin(rot_angle)),
        WINDOW_H/2 - (scroll_x*ZOOM*sin(rot_angle) + scroll_y*ZOOM*cos(rot_angle))
    )
    env.viewer.transform.set_rotation(rot_angle)

    arr = None
    win = env.viewer.window
    if mode != 'state_pixels':
        win.switch_to()
        win.dispatch_events()

    if mode=="rgb_array" or mode=="state_pixels":
        win.clear()
        t = env.viewer.transform
        if mode=='rgb_array':
            VP_W = VIDEO_W
            VP_H = VIDEO_H
        else:
            VP_W = STATE_W
            VP_H = STATE_H
        gl.glViewport(0, 0, VP_W, VP_H)

        render_objects()

        image_data = pyglet.image.get_buffer_manager().get_color_buffer().get_image_data()
        arr = np.fromstring(image_data.data, dtype=np.uint8, sep='')
        arr = arr.reshape(VP_H, VP_W, 4)
        arr = arr[::-1, :, 0:3]

    if mode=="rgb_array": # agent can call or not call base_env.render() itself when recording video.
        win.flip()

    if mode=='human':
        win.clear()
        t = env.viewer.transform
        gl.glViewport(0, 0, WINDOW_W, WINDOW_H)

        render_objects()

        win.flip()

    env.viewer.onetime_geoms = []
    return arr

def init_env_viewer(env):
    env.viewer = Viewer(WINDOW_W, WINDOW_H)
    env.viewer.reward_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 20.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))
    env.viewer.cum_reward_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 40.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))
    env.viewer.delta_path_prog_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 60.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))
    env.viewer.cross_track_error_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 80.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))
    env.viewer.speed_error_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 100.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))
    env.viewer.time_step_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 120.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))
    env.viewer.episode_text_field = pyglet.text.Label('0000', font_size=10,
                                            x=20, y=WINDOW_H - 140.00, anchor_x='left', anchor_y='center',
                                            color=(255, 0, 0, 255))

def _render_path(env):
    env.viewer.draw_polyline(env.path.path_points, linewidth=3, color=(0.3, 0.3, 0.3))

def _render_vessel(env):
    env.viewer.draw_polyline(env.vessel.path_taken, linewidth=3, color=(0.8, 0, 0))  # previous positions
    env.viewer.draw_shape([
            (-env.vessel.width, -env.vessel.width),
            (-env.vessel.width, env.vessel.width),
            (2 * env.vessel.width, env.vessel.width),
            (3 * env.vessel.width, 0),
            (2 * env.vessel.width, -env.vessel.width),
        ], env.vessel.position, env.vessel.heading, color=(0, 0, 0.8))  # ship
    env.viewer.draw_arrow(env.vessel.position, env.vessel.heading + pi + env.vessel.input[1]/4, length=2)

def _render_progress(env):
    p = env.path(env.path_prog[-1]).flatten()
    env.viewer.draw_circle(origin=p, radius=1, res=30, color=(0.8, 0.3, 0.3))

def _render_obstacles(env):
    for i, o in enumerate(env.obstacles):
        env.viewer.draw_circle(o.position, o.radius, color=(0.0, 1.0, 0.0))

def _render_tiles(env, win):
    global env_bg

    if env_bg is None:
        # Initialise background
        from pyglet.gl.gl import GLubyte
        data = np.zeros((int(2*PLAYFIELD), int(2*PLAYFIELD), 3))
        env_bg_h = data.shape[0]
        env_bg_w = data.shape[1]
        k = env_bg_h//100
        for x in range(0, data.shape[0], k):
            for y in range(0, data.shape[1], k):
                data[x:x+k, y:y+k, :] = np.array((
                    int(255*min(1.0, 0.3 + 0.025 * (np.random.random() - 0.5))),
                    int(255*min(1.0, 0.7 + 0.025 * (np.random.random() - 0.5))),
                    int(255*min(1.0, 0.8 + 0.025 * (np.random.random() - 0.5)))
                ))

        pixels = data.flatten().astype('int').tolist()
        raw_data = (GLubyte * len(pixels))(*pixels)
        bg = pyglet.image.ImageData(width=env_bg_w, height=env_bg_h, format='RGB', data=raw_data)
        if not os.path.exists('./tmp'):
            os.mkdir('./tmp')
        bg.save('./tmp/bg.png')
        env_bg = pyglet.sprite.Sprite(bg, x=-env_bg_w/2, y=-env_bg_h/2)
        env_bg.scale = 1

    env_bg.draw()

def _render_indicators(env, W, H):

    prog = W/40.0
    h = H/40.0
    boatw = 1.3*25
    gl.glBegin(gl.GL_QUADS)
    gl.glColor4f(0,0,0,1)
    gl.glVertex3f(W, 0, 0)
    gl.glVertex3f(W, 5*h, 0)
    gl.glVertex3f(0, 5*h, 0)
    gl.glVertex3f(0, 0, 0)
    gl.glEnd()

    def vertical_ind(place, val, color):
        gl.glBegin(gl.GL_QUADS)
        gl.glColor3f(*color)
        gl.glVertex3f((place+0)*prog, 2*h + h*val, 0)
        gl.glVertex3f((place+1)*prog, 2*h + h*val, 0)
        gl.glVertex3f((place+1)*prog, 2*h, 0)
        gl.glVertex3f((place+0)*prog, 2*h, 0)
        gl.glEnd()


    def horiz_ind(place, val, color):
        gl.glBegin(gl.GL_QUADS)
        gl.glColor4f(color[0], color[1], color[2], 1)
        gl.glVertex3f((place+0)*prog, 4*h, 0)
        gl.glVertex3f((place+val)*prog, 4*h, 0)
        gl.glVertex3f((place+val)*prog, 2*h, 0)
        gl.glVertex3f((place+0)*prog, 2*h, 0)
        gl.glEnd()

    def gl_boat(x, y):
        # Draw boat shape
        gl.glBegin(gl.GL_LINES)
        gl.glColor3f(0.9, 0.9, 0.9)
        gl.glVertex2f(x, y)
        gl.glVertex2f(x + boatw, y)
        gl.glVertex2f(x + boatw, y)
        gl.glVertex2f(x + boatw, y + 2 * h)
        gl.glVertex2f(x + boatw, y + 2 * h)
        gl.glVertex2f(x + boatw / 2, y + 2.5 * h)
        gl.glVertex2f(x + boatw / 2, y + 2.5 * h)
        gl.glVertex2f(x, y + 2*h)
        gl.glVertex2f(x, y + 2*h)
        gl.glVertex2f(x, y)
        gl.glEnd()

    def gl_arrow(x, y, angle, length, color=(0.9, 0.9, 0.9)):
        L = 50
        T = np.clip(7*length, 0, 7)
        hx, hy = x + length*L*cos(angle), y + length*L*sin(angle)

        gl.glEnable(gl.GL_LINE_SMOOTH)
        gl.glLineWidth(2)
        gl.glBegin(gl.GL_LINES)
        gl.glColor3f(*color)
        gl.glVertex2f(x, y)
        gl.glVertex2f(hx, hy)
        gl.glEnd()

        gl.glBegin(gl.GL_TRIANGLES)
        gl.glVertex2f(hx+T*cos(angle), hy+T*sin(angle))
        gl.glVertex2f(hx + T*cos(angle + 2*pi/3), hy + T*sin(angle + 2*pi/3))
        gl.glVertex2f(hx + T*cos(angle + 4*pi/3), hy + T*sin(angle + 4*pi/3))
        gl.glEnd()

    def obst_ind(place):
        gl_boat(place * prog, h)

        for obstacle in env.obstacles:
            heading = pi*obstacle[2*i]
            closeness = obstacle[2*i+1]
            gl_arrow(place * prog + boatw/2, 2*h,
                        angle=heading+pi/2,
                        length=np.clip(closeness, 0.1, 1),
                        color=(np.clip(1.2*closeness, 0, 1), 0.5, 0.1))
    scale = 3
    R = env.vessel.input[0]
    true_speed = np.sqrt(np.square(env.vessel.velocity[0]) + np.square(env.vessel.velocity[1]))
    ref_speed_error = env.past_obs[-1][0]
    vertical_ind(6, -scale*ref_speed_error, color=(np.clip(R, 0, 1), 0.5, 0.1))
    state_speed_error = env.past_obs[-1][0]
    vertical_ind(7, -scale*state_speed_error, color=(np.clip(true_speed, 0, 1), 0.6, 0.1))

    # Visualise the obstacles as seen by the vessel
    obst_ind(place=20)

    env.viewer.reward_text_field.text = "{:<40}{:2.2f}".format('Reward:', 
        env.past_rewards[-1] if len(env.past_rewards) else np.nan
    )
    env.viewer.reward_text_field.draw()
    env.viewer.cum_reward_text_field.text = "{:<40}{:2.2f}".format('Cumulative Reward:', env.cumulative_reward)
    env.viewer.cum_reward_text_field.draw()
    env.viewer.delta_path_prog_text_field.text = "{:<40}{:2.2f}".format('Delta Path Progression:', 
        env.path_prog[-1] - env.path_prog[-2] if len(env.path_prog) > 1 else np.nan
    )
    env.viewer.delta_path_prog_text_field.draw()
    env.viewer.cross_track_error_text_field.text = "{:<40}{:2.2f}".format('Cross Track Error:', 
        env.past_errors['cross_track'][-1] if len(env.past_errors['cross_track']) else np.nan
    )
    env.viewer.cross_track_error_text_field.draw()
    env.viewer.speed_error_text_field.text = "{:<40}{:2.2f}".format('Speed Error:', 
        env.past_errors['speed'][-1] if len(env.past_errors['speed']) else np.nan
    )
    env.viewer.speed_error_text_field.draw()
    env.viewer.time_step_text_field.text = "{:<40}{}".format('Time Step:', env.t_step)
    env.viewer.time_step_text_field.draw()
    env.viewer.episode_text_field.text = "{:<40}{}".format('Episode:', env.episode)
    env.viewer.episode_text_field.draw()