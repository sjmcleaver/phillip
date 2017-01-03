from ctypes import *
from ctype_util import *
from enum import IntEnum
import struct
import tempfile
import os
#import h5py
import pickle
from reward import computeRewards
import numpy as np
import itertools
import attr

@pretty_struct
class Stick(Structure):
  _fields = [
    ('x', c_float),
    ('y', c_float),
  ]

  def __init__(self, x=0.5, y=0.5):
    self.x = x
    self.y = y

  def reset(self):
    self.x = 0.5
    self.y = 0.5

@pretty_struct
class RealControllerState(Structure):
  _fields = [
    ('button_A', c_bool),
    ('button_B', c_bool),
    ('button_X', c_bool),
    ('button_Y', c_bool),
    ('button_Z', c_bool),
    ('button_L', c_bool),
    ('button_R', c_bool),
    ('button_START', c_bool),

    ('trigger_L', c_float),
    ('trigger_R', c_float),

    ('stick_MAIN', Stick),
    ('stick_C', Stick),
  ]

  def __init__(self):
    self.reset()

  def reset(self):
    "Resets controller to neutral position."
    self.button_A = False
    self.button_B = False
    self.button_X = False
    self.button_Y = False
    self.button_L = False
    self.button_R = False

    self.analog_L = 0.0
    self.analog_R = 0.0

    self.stick_MAIN.reset()
    self.stick_C.reset()
  
RealControllerState.neutral = RealControllerState()

@pretty_struct
class PlayerMemory(Structure):
  _fields = [
    ('percent', c_uint),
    ('stock', c_uint),
    # 1.0 is right, -1.0 is left
    ('facing', c_float),
    ('x', c_float),
    ('y', c_float),
    ('z', c_float),
    ('action_state', c_uint),
    ('action_counter', c_uint),
    ('action_frame', c_float),
    ('character', c_uint),
    ('invulnerable', c_bool),
    ('hitlag_frames_left', c_float),
    ('hitstun_frames_left', c_float),
    ('jumps_used', c_uint),
    ('charging_smash', c_bool),
    ('in_air', c_bool),
    ('speed_air_x_self', c_float),
    ('speed_ground_x_self', c_float),
    ('speed_y_self', c_float),
    ('speed_x_attack', c_float),
    ('speed_y_attack', c_float),
    ('shield_size', c_float),

    ('cursor_x', c_float),
    ('cursor_y', c_float),

    # NOTE: the sticks here are [-1, 1],
    # not [0, 1] like in pad.py
    ('controller', RealControllerState)
  ]

@pretty_struct
class GameMemory(Structure):
  _fields = [
    ('players', PlayerMemory * 4),

    ('frame', c_uint),
    ('menu', c_uint),
    ('stage', c_uint)
  ]

class SimpleButton(IntEnum):
  NONE = 0
  A = 1
  B = 2
  Z = 3
  Y = 4
  L = 5
  
@attr.s
class SimpleController:
  button = attr.ib(default=SimpleButton.NONE)
  x = attr.ib(default=0.5)
  y = attr.ib(default=0.5)
  
  def realController(self):
    controller = RealControllerState()
    if self.button is not SimpleButton.NONE:
      setattr(controller, "button_%s" % self.button.name, True)

    controller.stick_MAIN.x = self.x
    controller.stick_MAIN.y = self.y
    return controller
  
  def banned(self, char):
    if char == 'peach':
      return self.button == SimpleButton.B and self.x == 0.5 and self.y == 0.5
    if char in ['sheik', 'zelda']:
      return self.button == SimpleButton.B and self.y == 0
    return False

axis_granularity = 3
axis_positions = np.linspace(0, 1, axis_granularity)

#diagonal_sticks = itertools.product(axis_positions, repeat=2)
diagonal_controllers = [SimpleController(*args) for args in itertools.product(SimpleButton, axis_positions, axis_positions)]
diagonal_size = len(diagonal_controllers)
real_diagonal_controllers = [c.realController() for c in diagonal_controllers]

class DiagonalAction:
  size = diagonal_size
  
  @staticmethod
  def send(index, pad, char=None):
    controller = diagonal_controllers[index]
    if controller.banned(char):
      pad.send_controller(RealControllerState.neutral)
    else:
      pad.send_controller(real_diagonal_controllers[index])

actionTypes = dict(
  diagonal = DiagonalAction,
)

@pretty_struct
class SimpleStateAction(Structure):
  _fields = [
    ('state', GameMemory),
    ('prev_action', c_uint),
    ('action', c_uint),
  ]

intStruct = struct.Struct('i')

def readInt(f):
  return intStruct.unpack(f.read(4))[0]

def writeStateActions(filename, state_actions):
  with tempfile.NamedTemporaryFile(dir=os.path.dirname(filename), delete=False) as tf:
    tf.write(intStruct.pack(len(state_actions)))
    tf.write(state_actions)
    tempname = tf.name
  os.rename(tempname, filename)

def readStateActions(filename):
  with open(filename, 'rb') as f:
    size = readInt(f)
    state_actions = (size * SimpleStateAction)()
    f.readinto(state_actions)

    if len(f.read()) > 0:
      raise Exception(filename + " too long!")

    return state_actions

# prepares an experience for pickling
def prepareStateActions(state_actions):
  vectorized = vectorizeCTypes(SimpleStateAction, state_actions)
  
  #import ipdb; ipdb.set_trace()
  
  states = vectorized['state']

  rewards = computeRewards(state_actions)
  
  vectorized['reward'] = rewards
  
  return vectorized
  
def writeStateActions_pickle(filename, state_actions):
  with tempfile.NamedTemporaryFile(dir=os.path.dirname(filename), delete=False) as tf:
    prepared = prepareStateActions(state_actions)
    pickle.dump(prepared, tf)
    tempname = tf.name
  os.rename(tempname, filename)

def readStateActions_pickle(filename):
  with open(filename, 'rb') as f:
    return pickle.load(f)

# TODO: replace pickle with hdf5
def writeStateActions_HDF5(filename, state_actions):
  with tempfile.NamedTemporaryFile(dir=os.path.dirname(filename), delete=False) as tf:
    tf.write(intStruct.pack(len(state_actions)))
    tf.write(state_actions)
    tempname = tf.name
  os.rename(tempname, filename)

def readStateActions_HDF5(filename):
  with open(filename, 'rb') as f:
    size = readInt(f)
    state_actions = (size * SimpleStateAction)()
    f.readinto(state_actions)

    if len(f.read()) > 0:
      raise Exception(filename + " too long!")

    return state_actions
