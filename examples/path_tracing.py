import taichi as ti
import taichi_three as t3
import numpy as np

res = 512, 512
ti.init(ti.cpu)

scene = t3.Scene()
cornell = t3.readobj('assets/cornell.obj', orient='-xyz')
cube = t3.Geometry.cube()
model = t3.Model.from_obj(cornell)
model.material = t3.Material(t3.IdealRT(
    diffuse=t3.Constant(1.0),
    emission=t3.Constant(0.0),
))
scene.add_model(model)
light = t3.Model.from_obj(cube)
light.material = t3.Material(t3.IdealRT(
    diffuse=t3.Constant(0.0),
    emission=t3.Constant(1.0),
    emission_color=t3.Constant(8.0),
))
scene.add_model(light)
camera = t3.RTCamera(res=res)
camera.ctl = t3.CameraCtl(pos=[0, 2, 6], target=[0, 2, 0])
scene.add_camera(camera)
accumator = t3.Accumator(camera.res)

light.L2W[None] = t3.translate(0, 4, 0) @ t3.scale(0.2, 0.2, 0.08)
gui = ti.GUI('Model', camera.res)
while gui.running:
    gui.get_event(None)
    gui.running = not gui.is_pressed(ti.GUI.ESCAPE)
    if camera.from_mouse(gui):
        accumator.reset()
    accumator.render(camera, 3)
    gui.set_image(accumator.buf)
    gui.show()
