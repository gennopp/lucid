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


"""Provides render_vis() for actually rendering visualizations.

This module primarily provides render_vis() for rendering visualizations.
It also provides some utilities in case you need to create your own rendering
function.
"""
from __future__ import print_function

from cStringIO import StringIO
from IPython.display import display
from IPython.display import Image

import numpy as np
import PIL.Image
import tensorflow as tf

import objectives 
import param 
import transform 

# pylint: disable=invalid-name


def render_vis(model, objective_f, param_f=None, optimizer=None,
               transforms=None, thresholds=(512,),
               print_objectives=None, verbose=True,):
  """Flexible optimization-base feature vis.

  There's a lot of ways one might wish to customize otpimization-based
  feature visualization. It's hard to create an abstraction that stands up
  to all the things one might wish to try.

  This function probably can't do *everything* you want, but it's much more
  flexible than a naive attempt. The basic abstraction is to split the problem
  into several parts. Consider the rguments:

  Args:
    model: The model to be visualized, from Alex' modelzoo.
    objective_f: The objective our visualization maximizes.
      See the objectives module for more details.
    param_f: Paramaterization of the image we're optimizing.
      See the paramaterization module for more details.
      Defaults to a naively paramaterized [1, 128, 128, 3] image.
    optimizer: Optimizer to optimize with. Either tf.train.Optimizer instance,
      or a function from (graph, sess) to such an instance.
      Defaults to Adam with lr .05.
    transforms: A list of stochastic transformations that get composed,
      which our visualization should robustly activate the network against.
      See the transform module for more details.
      Defaults to [transform.jitter(8)].
    thresholds: A list of numbers of optimization steps, at which we should
      save (and display if verbose=True) the visualization.
    print_objectives: A list of objectives separate from those being optimized,
      whose values get logged during the optimization.
    verbose: Should we display the visualization when we hit a threshold?
      This should only be used in IPython.
  Returns:
    2D array of optimization results containing of evaluations of supplied
    param_f snapshotted at specified thresholds. Usually that will mean one or
    multiple channel visualizations stacked on top of each other.
  """

  with tf.Graph().as_default() as graph, tf.Session() as sess:

    T = make_vis_T(model, objective_f, param_f, optimizer, transforms)
    print_objective_func = make_print_objective_func(print_objectives, T)
    loss, vis_op, t_image = T("loss"), T("vis_op"), T("input")
    tf.global_variables_initializer().run()

    images = []
    try:
      for i in xrange(max(thresholds)+1):
        loss_, _ = sess.run([loss, vis_op])
        if i in thresholds:
          vis = t_image.eval()
          images.append(vis)
          if verbose:
            print(i, loss_)
            print_objective_func(sess)
            showarray(np.hstack(vis), "png")
    except KeyboardInterrupt:
      print("Interrupted optimization at step {:d}.".format(i+1))
      vis = t_image.eval()
      showarray(np.hstack(vis), "png")

    return images


def make_vis_T(model, objective_f, param_f=None, optimizer=None,
               transforms=None):
  """Even more flexible optimization-base feature vis.

  This function is the inner core of render_vis(), and can be used
  when render_vis() isn't flexible enough. Unfortunately, it's a bit more
  tedious to use:

  >  with tf.Graph().as_default() as graph, tf.Session() as sess:
  >
  >    T = make_vis_T(model, "mixed4a_pre_relu:0")
  >    tf.initialize_all_variables().run()
  >
  >    for i in range(10):
  >      T("vis_op").run()
  >      showarray(T("input").eval()[0])

  This approach allows more control over how the visualizaiton is displayed
  as it renders. It also allows a lot more flexibility in constructing
  objectives / params because the session is already in scope.


  Args:
    model: The model to be visualized, from Alex' modelzoo.
    objective_f: The objective our visualization maximizes.
      See the objectives module for more details.
    param_f: Paramaterization of the image we're optimizing.
      See the paramaterization module for more details.
      Defaults to a naively paramaterized [1, 128, 128, 3] image.
    optimizer: Optimizer to optimize with. Either tf.train.Optimizer instance,
      or a function from (graph, sess) to such an instance.
      Defaults to Adam with lr .05.
    transforms: A list of stochastic transformations that get composed,
      which our visualization should robustly activate the network against.
      See the transform module for more details.
      Defaults to [transform.jitter(8)].

  Returns:
    A function T, which allows access to:
      * T("vis_op") -- the operation for to optimize the visualization
      * T("input") -- the visualization itself
      * T("loss") -- the loss for the visualization
      * T(layer) -- any layer inside the network
  """

  # pylint: disable=unused-variable
  t_image = make_t_image(param_f)
  objective_f = objectives.as_objective(objective_f)
  transform_f = make_transform_f(transforms)
  optimizer = make_optimizer(optimizer, [])

  T = import_model(model, transform_f(t_image), t_image)
  loss = objective_f(T)

  global_step = tf.Variable(0, trainable=False, name="global_step")
  vis_op = optimizer.minimize(-loss, global_step=global_step)

  local_vars = locals()
  # pylint: enable=unused-variable

  def T2(name):
    if name in local_vars:
      return local_vars[name]
    else: return T(name)

  return T2


def make_print_objective_func(print_objectives, T):
  print_objectives = print_objectives or []
  po_descriptions = [obj.description for obj in print_objectives]
  pos = [obj(T) for obj in print_objectives]

  def print_objective_func(sess):
    pos_results = sess.run(pos)
    for k, v, i in zip(po_descriptions, pos_results, range(len(pos_results))):
      print("{:02d}: {}: {:7.2f}".format(i+1, k, v))

  return print_objective_func

# pylint: enable=invalid-name


def make_t_image(param_f):
  if param_f is None:
    t_image = param.rgb_sigmoid(param.naive([1, 128, 128, 3]))
  elif callable(param_f):
    t_image = param_f()
  elif isinstance(param_f, tf.Tensor):
    t_image = param_f
  else:
    raise TypeError("Incompatible type for param_f, " + str(type(param_f)) )

  if not isinstance(t_image, tf.Tensor):
    raise TypeError("param_f should produce a Tensor, but instead created a "
                   + str(type(t_image)) )
  elif t_image.graph != tf.get_default_graph():
    raise TypeError("""param_f produced a t_image tensor belonging to a graph
                     that isn't the default graph for rendering. Did you
                     accidentally use render_vis when you meant to use
                     make_vis_T?""")
  else:
    return t_image


def make_transform_f(transforms):
  if type(transforms) is not list:
    transforms = [transform.jitter(8)]
  transform_f = transform.compose(transforms)
  return transform_f


def make_optimizer(optimizer, args):
  if optimizer is None:
    return tf.train.AdamOptimizer(0.05)
  elif callable(optimizer):
    return optimizer(*args)
  elif isinstance(optimizer, tf.train.Optimizer):
    return optimizer
  else:
    raise ("Could not convert optimizer argument to usable optimizer. "
           "Needs to be one of None, function from (graph, sess) to "
           "optimizer, or tf.train.Optimizer instance.")


def import_model(model, t_image, t_image_raw):

  model.import_graph(t_image, forget_xy_shape=True)

  def T(layer):
    if layer == "input": return t_image_raw
    if layer == "labels": return model.labels
    return t_image.graph.get_tensor_by_name("import/%s:0"%layer)

  if model.__class__.__name__ == "GoogleNet":
    names = ["mixed3a", "mixed3b",
             "mixed4a", "mixed4b", "mixed4c", "mixed4d", "mixed4e",
             "mixed5a", "mixed5b"]

    exts = ["1x1_pre_relu", "3x3_pre_relu",
            "5x5_pre_relu", "pool_reduce_pre_relu"]

    for name in names:
      concat_name = "import/"+name+"_pre_relu"
      tf.concat([T(name+"_"+ext) for ext in exts], 3, name=concat_name)

  return T


def showarray(a, fmt="png", s=None):
  # squeeze helps both with batch=1 and B/W
  a = np.squeeze(np.asarray(a))

  # check dtype
  if a.dtype in [np.float32, np.float64]:
    a = np.uint8(np.clip(a, 0, 1)*255)

  # infer mode from shape
  if len(a.shape) == 2:
    mode = "L"
  else:
    depth = a.shape[-1]
    if depth == 3:
      mode = "RGB"
    elif depth == 4:
      mode = "RGBA"
    else:
      raise "showarray only supports 2D, 3D & 4D images, not this shape: " + a.shape

  # serialize
  f = StringIO()
  pil = PIL.Image.fromarray(a, mode=mode)
  pil.save(f, fmt)
  data = f.getvalue()
  display(Image(data=data))
