# Copyright 2018 The Deepviz Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================


import urllib2
import tensorflow as tf


def read_resource(path):
  if '://' in path:
    protocol, resource = path.split('://')
    if protocol == 'gs':
      url = 'https://storage.googleapis.com/' + resource
    else:
      url = resource
    return urllib2.urlopen(url).read()
  else:
    return tf.gfile.GFile(path).read()

def load_graphdef(model_url, reset_device=True):
  """Load GraphDef from a binary proto file."""
  graph_def_str = read_resource(model_url)
  graph_def = tf.GraphDef.FromString(graph_def_str)
  if reset_device:
    for n in graph_def.node:
      n.device = ""
  return graph_def

def forget_xy(t):
  """Forget sizes of dimensions [1, 2] of a 4d tensor."""
  zero = tf.identity(0)
  return t[:, zero:, zero:, :]
