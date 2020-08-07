import math
import taichi as ti
import taichi_glsl as ts


@ti.data_oriented
class Geometry(ts.TaichiClass):
    @ti.func
    def render(self):
        for I in ti.grouped(ti.ndrange(*self.loop_range().shape())):
            self.subscript(I).do_render()

    def subscript(self, I):
        ret = self._subscript(I)
        try:
            ret.model = self.model
        except AttributeError:
            pass
        return ret

    def do_render(self):
        raise NotImplementedError


@ti.data_oriented
class Vertex(Geometry):
    @property
    def pos(self):
        return self.entries[0]

    @classmethod
    def _var(cls, shape=None):
        return ti.Vector.var(3, ti.f32, shape)


@ti.data_oriented
class Line(Geometry):
    @property
    def idx(self):
        return self.entries[0]

    @classmethod
    def _var(cls, shape=None):
        return ti.Vector.var(2, ti.i32, shape)

    @ti.func
    def vertex(self, i: ti.template()):
        model = self.model
        return model.vertices[self.idx[i]]

    @ti.func
    def do_render(self):
        scene = self.model.scene
        W = 1
        A = scene.uncook_coor(scene.camera.untrans_pos(self.vertex(0).pos))
        B = scene.uncook_coor(scene.camera.untrans_pos(self.vertex(1).pos))
        M, N = int(ti.floor(min(A, B) - W)), int(ti.ceil(max(A, B) + W))
        for X in ti.grouped(ti.ndrange((M.x, N.x), (M.y, N.y))):
            P = B - A
            udf = (ts.cross(X, P) + ts.cross(B, A))**2 / P.norm_sqr()
            XoP = ts.dot(X, P)
            AoB = ts.dot(A, B)
            if XoP > B.norm_sqr() - AoB:
                udf = (B - X).norm_sqr()
            elif XoP < AoB - A.norm_sqr():
                    udf = (A - X).norm_sqr()
            if udf < 0:
                scene.img[X] = ts.vec3(1.0)
            elif udf < W**2:
                t = ts.smoothstep(udf, 0, W**2)
                ti.atomic_min(scene.img[X], ts.vec3(t))


@ti.data_oriented
class Face(Geometry):
    @property
    def idx(self):
        return self.entries[0]

    @classmethod
    def _var(cls, shape=None):
        return ti.Vector.var(3, ti.i32, shape)

    @ti.func
    def vertex(self, i: ti.template()):
        model = self.model
        return model.vertices[self.idx[i]]

    @ti.func
    def do_render(self):
        model = self.model
        scene = model.scene
        L2W = model.L2W
        # object to world
        a = scene.camera.untrans_pos(L2W @ self.vertex(0).pos)
        b = scene.camera.untrans_pos(L2W @ self.vertex(1).pos)
        c = scene.camera.untrans_pos(L2W @ self.vertex(2).pos)
        # NOTE: the normal computation indicates that 
        # a front-facing face should be COUNTER-CLOCKWISE, i.e., glFrontFace(GL_CCW​);
        # this is to be compatible with obj model loading.
        normal = ts.normalize(ts.cross(a - b, a - c))
        pos = (a + b + c) / 3
        # backface culling
        if (ts.dot(pos, normal) <= 0):
            # shading
            light_dir = scene.camera.untrans_dir(scene.light_dir[None])
            color = scene.opt.render_func(pos, normal, ts.vec3(0.0), light_dir)
            color = scene.opt.pre_process(color)
            # screen projection
            # dirty workaround for projection
            # the proper implementation is through projection matrix
            fov = ti.static(ti.tan(scene.camera.fov * math.pi / 180))
            #print(pos, normal)  
            a.xy /= a.z * fov
            b.xy /= b.z * fov
            c.xy /= c.z * fov

            A = scene.uncook_coor(a)
            B = scene.uncook_coor(b)
            C = scene.uncook_coor(c)
            B_A = B - A
            C_B = C - B
            A_C = A - C
            
            W = 1
            # screen space bounding box
            M, N = int(ti.floor(min(A, B, C) - W)), int(ti.ceil(max(A, B, C) + W))
            M.x, N.x = min(max(M.x, 0), scene.img.shape[0]), min(max(N.x, 0), scene.img.shape[1])
            M.y, N.y = min(max(M.y, 0), scene.img.shape[0]), min(max(N.y, 0), scene.img.shape[1])
            scr_norm = ts.cross(A_C, B_A)
            for X in ti.grouped(ti.ndrange((M.x, N.x), (M.y, N.y))):
                # barycentric coordinates
                X_A = X - A
                u_c = ts.cross(B_A, X_A) / scr_norm
                u_b = ts.cross(A_C, X_A) / scr_norm
                u_a = 1. - u_c - u_b
                # draw
                if u_a >= 0 and u_b >= 0 and u_c >= 0\
                        and 0 < X[0] < scene.img.shape[0] and 0 < X[1] < scene.img.shape[1]:
                    zindex = a.z * u_a + b.z * u_b + c.z * u_c
                    zstep = zindex - ti.atomic_min(scene.zbuf[X], zindex)
                    if zstep <= 0:
                        scene.img[X] = color
