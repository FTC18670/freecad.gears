# -*- coding: utf-8 -*-
# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

from __future__ import division
import os

import numpy as np
import math
from pygears import __version__
from pygears.involute_tooth import InvoluteTooth, InvoluteRack
from pygears.cycloid_tooth import CycloidTooth
from pygears.bevel_tooth import BevelTooth
from pygears._functions import rotation3D, rotation, reflection, arc_from_points_and_center


import FreeCAD as App
import Part
from Part import BSplineCurve, Shape, Wire, Face, makePolygon, \
    makeLoft, Line, BSplineSurface, \
    makePolygon, makeHelix, makeShell, makeSolid


__all__ = ["InvoluteGear",
           "CycloidGear",
           "BevelGear",
           "InvoluteGearRack",
           "CrownGear",
           "WormGear",
           "HypoCycloidGear",
           "ViewProviderGear"]


def fcvec(x):
    if len(x) == 2:
        return(App.Vector(x[0], x[1], 0))
    else:
        return(App.Vector(x[0], x[1], x[2]))


class ViewProviderGear(object):
    def __init__(self, obj):
        ''' Set this object to the proxy object of the actual view provider '''
        obj.Proxy = self

    def attach(self, vobj):
        self.vobj = vobj

    def getIcon(self):
        __dirname__ = os.path.dirname(__file__)
        return(os.path.join(__dirname__, "icons", "involutegear.svg"))

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

class BaseGear(object):
    def __init__(self, obj):
        obj.addProperty("App::PropertyString", "version", "version", "freecad.gears-version", 1)
        obj.version = __version__
        self.make_attachable(obj)

    def make_attachable(self, obj):
        # Needed to make this object "attachable",
        # aka able to attach parameterically to other objects
        # cf. https://wiki.freecadweb.org/Scripted_objects_with_attachment
        if int(App.Version()[1]) >= 19:
            obj.addExtension('Part::AttachExtensionPython')
        else:
            obj.addExtension('Part::AttachExtensionPython', obj)
        # unveil the "Placement" property, which seems hidden by default in PartDesign
        obj.setEditorMode('Placement', 0) #non-readonly non-hidden

    def execute(self, fp):
        # checksbackwardcompatibility:
        if not hasattr(fp, "positionBySupport"):
            self.make_attachable(fp)
        fp.positionBySupport()
        gear_shape = self.generate_gear_shape(fp)
        if hasattr(fp, "BaseFeature") and fp.BaseFeature != None:
            # we're inside a PartDesign Body, thus need to fuse with the base feature
            gear_shape.Placement = fp.Placement # ensure the gear is placed correctly before fusing
            result_shape = fp.BaseFeature.Shape.fuse(gear_shape)
            result_shape.transformShape(fp.Placement.inverse().toMatrix(), True) # account for setting fp.Shape below moves the shape to fp.Placement, ignoring its previous placement
            fp.Shape = result_shape
        else:
            fp.Shape = gear_shape

    def generate_gear_shape(self, fp):
        """
        This method has to return the TopoShape of the gear.
        """
        raise NotImplementedError("generate_gear_shape not implemented")

class InvoluteGear(BaseGear):

    """FreeCAD gear"""

    def __init__(self, obj):
        super(InvoluteGear, self).__init__(obj)
        self.involute_tooth = InvoluteTooth()
        obj.addProperty(
            "App::PropertyBool", "simple", "precision", "simple")
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyLength", "module", "gear_parameter", "normal module if properties_from_tool=True, \
                                                                else it's the transverse module.")
        obj.addProperty(
            "App::PropertyBool", "undercut", "gear_parameter", "undercut")
        obj.addProperty(
            "App::PropertyFloat", "shift", "gear_parameter", "shift")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyAngle", "pressure_angle", "involute_parameter", "pressure angle")
        obj.addProperty(
            "App::PropertyFloat", "clearance", "gear_parameter", "clearance")
        obj.addProperty("App::PropertyInteger", "numpoints",
                        "precision", "number of points for spline")
        obj.addProperty(
            "App::PropertyAngle", "beta", "gear_parameter", "beta ")
        obj.addProperty(
            "App::PropertyBool", "double_helix", "gear_parameter", "double helix")
        obj.addProperty(
            "App::PropertyLength", "backlash", "tolerance", "backlash")
        obj.addProperty(
            "App::PropertyBool", "reversed_backlash", "tolerance", "backlash direction")
        obj.addProperty(
            "App::PropertyFloat", "head", "gear_parameter", "head_value * modul_value = additional length of head")
        obj.addProperty(
            "App::PropertyBool", "properties_from_tool", "gear_parameter", "if beta is given and properties_from_tool is enabled, \
            gear parameters are internally recomputed for the rotated gear")
        obj.addProperty("App::PropertyPythonObject",
                        "gear", "gear_parameter", "test")
        obj.addProperty("App::PropertyLength", "dw",
                        "computed", "pitch diameter", 1)
        obj.addProperty("App::PropertyLength", "transverse_pitch",
                        "computed", "transverse_pitch", 1)
        self.add_limiting_diameter_properties(obj)
        obj.gear = self.involute_tooth
        obj.simple = False
        obj.undercut = False
        obj.teeth = 15
        obj.module = '1. mm'
        obj.shift = 0.
        obj.pressure_angle = '20. deg'
        obj.beta = '0. deg'
        obj.height = '5. mm'
        obj.clearance = 0.25
        obj.head = 0.
        obj.numpoints = 6
        obj.double_helix = False
        obj.backlash = '0.00 mm'
        obj.reversed_backlash = False
        obj.properties_from_tool = False
        self.obj = obj
        obj.Proxy = self

    def add_limiting_diameter_properties(self, obj):
        obj.addProperty("App::PropertyLength", "da",
                        "computed", "outside diameter", 1)
        obj.addProperty("App::PropertyLength", "df",
                        "computed", "root diameter", 1)

    def generate_gear_shape(self, fp):
        fp.gear.double_helix = fp.double_helix
        fp.gear.m_n = fp.module.Value
        fp.gear.z = fp.teeth
        fp.gear.undercut = fp.undercut
        fp.gear.shift = fp.shift
        fp.gear.pressure_angle = fp.pressure_angle.Value * np.pi / 180.
        fp.gear.beta = fp.beta.Value * np.pi / 180
        fp.gear.clearance = fp.clearance
        fp.gear.backlash = fp.backlash.Value * \
            (-fp.reversed_backlash + 0.5) * 2.
        fp.gear.head = fp.head
        # checksbackwardcompatibility:
        if "properties_from_tool" in fp.PropertiesList:
            fp.gear.properties_from_tool = fp.properties_from_tool
        fp.gear._update()

        # computed properties
        fp.dw = "{}mm".format(fp.gear.dw)
        fp.transverse_pitch = "{}mm".format(fp.gear.pitch)
        # checksbackwardcompatibility:
        if not "da" in fp.PropertiesList:
            self.add_limiting_diameter_properties(fp)
        fp.da = "{}mm".format(fp.gear.da)
        fp.df = "{}mm".format(fp.gear.df)

        pts = fp.gear.points(num=fp.numpoints)
        rotated_pts = pts
        rot = rotation(-fp.gear.phipart)
        for i in range(fp.gear.z - 1):
            rotated_pts = list(map(rot, rotated_pts))
            pts.append(np.array([pts[-1][-1], rotated_pts[0][0]]))
            pts += rotated_pts
        pts.append(np.array([pts[-1][-1], pts[0][0]]))
        if not fp.simple:
            wi = []
            for i in pts:
                out = BSplineCurve()
                out.interpolate(list(map(fcvec, i)))
                wi.append(out.toShape())
            wi = Wire(wi)
            if fp.height.Value == 0:
                return wi
            elif fp.beta.Value == 0:
                sh = Face(wi)
                return sh.extrude(App.Vector(0, 0, fp.height.Value))
            else:
                return helicalextrusion(
                    wi, fp.height.Value, fp.height.Value * np.tan(fp.gear.beta) * 2 / fp.gear.d, fp.double_helix)
        else:
            rw = fp.gear.dw / 2
            return Part.makeCylinder(rw, fp.height.Value)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class InvoluteGearRack(BaseGear):

    """FreeCAD gear rack"""

    def __init__(self, obj):
        super(InvoluteGearRack, self).__init__(obj)
        self.involute_rack = InvoluteRack()
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyLength", "module", "gear_parameter", "module")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyLength", "thickness", "gear_parameter", "thickness")
        obj.addProperty(
            "App::PropertyAngle", "beta", "gear_parameter", "beta ")
        obj.addProperty(
            "App::PropertyAngle", "pressure_angle", "involute_parameter", "pressure angle")
        obj.addProperty(
            "App::PropertyBool", "double_helix", "gear_parameter", "double helix")
        obj.addProperty(
            "App::PropertyFloat", "head", "gear_parameter", "head * module = additional length of head")
        obj.addProperty(
            "App::PropertyFloat", "clearance", "gear_parameter", "clearance * module = additional length of foot")
        obj.addProperty(
            "App::PropertyBool", "properties_from_tool", "gear_parameter", "if beta is given and properties_from_tool is enabled, \
            gear parameters are internally recomputed for the rotated gear")
        obj.addProperty("App::PropertyLength", "transverse_pitch",
            "computed", "pitch in the transverse plane", 1)
        obj.addProperty("App::PropertyBool", "add_endings", "gear_parameter", "if enabled the total length of the rack is teeth x pitch, \
            otherwise the rack starts with a tooth-flank")
        obj.addProperty(
            "App::PropertyBool", "simplified", "gear_parameter", "if enabled the rack is drawn with a constant number of \
            teeth to avoid topologic renaming.")
        obj.addProperty("App::PropertyPythonObject", "rack", "test", "test")
        obj.rack = self.involute_rack
        obj.teeth = 15
        obj.module = '1. mm'
        obj.pressure_angle = '20. deg'
        obj.height = '5. mm'
        obj.thickness = '5 mm'
        obj.beta = '0. deg'
        obj.clearance = 0.25
        obj.head = 0.
        obj.properties_from_tool = True
        obj.add_endings = True
        obj.simplified = False
        self.obj = obj
        obj.Proxy = self

    def generate_gear_shape(self, fp):
        fp.rack.m = fp.module.Value
        fp.rack.z = fp.teeth
        fp.rack.pressure_angle = fp.pressure_angle.Value * np.pi / 180.
        fp.rack.thickness = fp.thickness.Value
        fp.rack.beta = fp.beta.Value * np.pi / 180.
        fp.rack.head = fp.head
        # checksbackwardcompatibility:
        if "clearance" in fp.PropertiesList:
            fp.rack.clearance = fp.clearance
        if "properties_from_tool" in fp.PropertiesList:
            fp.rack.properties_from_tool = fp.properties_from_tool
        if "add_endings" in fp.PropertiesList:
            fp.rack.add_endings = fp.add_endings
        if "simplified" in fp.PropertiesList:
            fp.rack.simplified = fp.simplified
        fp.rack._update()

        # computed properties
        if "transverse_pitch" in fp.PropertiesList:
            fp.transverse_pitch = "{} mm".format(fp.rack.compute_properties()[2])

        pts = fp.rack.points()
        pol = Wire(makePolygon(list(map(fcvec, pts))))
        if fp.height.Value == 0:
            return pol
        elif fp.beta.Value == 0:
            face = Face(Wire(pol))
            return face.extrude(fcvec([0., 0., fp.height.Value]))
        elif fp.double_helix:
            beta = fp.beta.Value * np.pi / 180.
            pol2 = Part.Wire(pol)
            pol2.translate(
                fcvec([0., np.tan(beta) * fp.height.Value / 2, fp.height.Value / 2]))
            pol3 = Part.Wire(pol)
            pol3.translate(fcvec([0., 0., fp.height.Value]))
            return makeLoft([pol, pol2, pol3], True, True)
        else:
            beta = fp.beta.Value * np.pi / 180.
            pol2 = Part.Wire(pol)
            pol2.translate(
                fcvec([0., np.tan(beta) * fp.height.Value, fp.height.Value]))
            return makeLoft([pol, pol2], True)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CrownGear(BaseGear):
    def __init__(self, obj):
        super(CrownGear, self).__init__(obj)
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty("App::PropertyInteger",
                        "other_teeth", "gear_parameter", "number of teeth of other gear")
        obj.addProperty(
            "App::PropertyLength", "module", "gear_parameter", "module")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyLength", "thickness", "gear_parameter", "thickness")
        obj.addProperty(
            "App::PropertyAngle", "pressure_angle", "involute_parameter", "pressure angle")
        obj.addProperty("App::PropertyInteger",
                        "num_profiles", "accuracy", "number of profiles used for loft")
        obj.addProperty("App::PropertyBool",
                        "preview_mode", "preview", "if true no boolean operation is done")
        obj.teeth = 15
        obj.other_teeth = 15
        obj.module = '1. mm'
        obj.pressure_angle = '20. deg'
        obj.height = '2. mm'
        obj.thickness = '5 mm'
        obj.num_profiles = 4
        obj.preview_mode = True
        self.obj = obj
        obj.Proxy = self

        App.Console.PrintMessage("Gear module: Crown gear created, preview_mode = true for improved performance. "\
                                 "Set preview_mode property to false when ready to cut teeth.")

    def profile(self, m, r, r0, t_c, t_i, alpha_w, y0, y1, y2):
        r_ew = m * t_i / 2

        # 1: modifizierter Waelzkreisdurchmesser:
        r_e = r / r0 * r_ew

        # 2: modifizierter Schraegungswinkel:
        alpha = np.arccos(r0 / r * np.cos(alpha_w))

        # 3: winkel phi bei senkrechter stellung eines zahns:
        phi = np.pi / t_i / 2 + (alpha - alpha_w) + \
            (np.tan(alpha_w) - np.tan(alpha))

        # 4: Position des Eingriffspunktes:
        x_c = r_e * np.sin(phi)
        dy = -r_e * np.cos(phi) + r_ew

        # 5: oberer Punkt:
        b = y1 - dy
        a = np.tan(alpha) * b
        x1 = a + x_c

        # 6: unterer Punkt
        d = y2 + dy
        c = np.tan(alpha) * d
        x2 = x_c - c

        r *= np.cos(phi)
        pts = [
            [-x1, r, y0],
            [-x2, r, y0 - y1 - y2],
            [x2, r, y0 - y1 - y2],
            [x1, r, y0]
        ]
        pts.append(pts[0])
        return pts

    def generate_gear_shape(self, fp):
        inner_diameter = fp.module.Value * fp.teeth
        outer_diameter = inner_diameter + fp.height.Value * 2
        inner_circle = Part.Wire(Part.makeCircle(inner_diameter / 2.))
        outer_circle = Part.Wire(Part.makeCircle(outer_diameter / 2.))
        inner_circle.reverse()
        face = Part.Face([outer_circle, inner_circle])
        solid = face.extrude(App.Vector([0., 0., -fp.thickness.Value]))
        if fp.preview_mode:
            return solid

        # cutting obj
        alpha_w = np.deg2rad(fp.pressure_angle.Value)
        m = fp.module.Value
        t = fp.teeth
        t_c = t
        t_i = fp.other_teeth
        rm = inner_diameter / 2
        y0 = m * 0.5
        y1 = m + y0
        y2 = m
        r0 = inner_diameter / 2 - fp.height.Value * 0.1
        r1 = outer_diameter / 2 + fp.height.Value * 0.3
        polies = []
        for r_i in np.linspace(r0, r1, fp.num_profiles):
            pts = self.profile(m, r_i, rm, t_c, t_i, alpha_w, y0, y1, y2)
            poly = Wire(makePolygon(list(map(fcvec, pts))))
            polies.append(poly)
        loft = makeLoft(polies, True)
        rot = App.Matrix()
        rot.rotateZ(2 * np.pi / t)
        cut_shapes = []
        for _ in range(t):
            loft = loft.transformGeometry(rot)
            cut_shapes.append(loft)
        return solid.cut(cut_shapes)

    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass


class CycloidGear(BaseGear):
    """FreeCAD gear"""

    def __init__(self, obj):
        super(CycloidGear, self).__init__(obj)
        self.cycloid_tooth = CycloidTooth()
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyLength", "module", "gear_parameter", "module")
        obj.addProperty(
            "App::PropertyLength", "inner_diameter", "cycloid_parameter", "inner_diameter (hypocycloid)")
        obj.addProperty(
            "App::PropertyLength", "outer_diameter", "cycloid_parameter", "outer_diameter (epicycloid)")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyBool", "double_helix", "gear_parameter", "double helix")
        obj.addProperty(
            "App::PropertyFloat", "clearance", "gear_parameter", "clearance")
        self._add_head_property(obj)
        obj.addProperty("App::PropertyInteger", "numpoints",
                        "precision", "number of points for spline")
        obj.addProperty("App::PropertyAngle", "beta", "gear_parameter", "beta")
        obj.addProperty(
            "App::PropertyLength", "backlash", "gear_parameter", "backlash in mm")
        obj.addProperty("App::PropertyPythonObject", "gear",
                        "gear_parameter", "the python object")
        obj.gear = self.cycloid_tooth
        obj.teeth = 15
        obj.module = '1. mm'
        obj.inner_diameter = '5 mm'
        obj.outer_diameter = '5 mm'
        obj.beta = '0. deg'
        obj.height = '5. mm'
        obj.clearance = 0.25
        obj.numpoints = 15
        obj.backlash = '0.00 mm'
        obj.double_helix = False
        obj.Proxy = self

    def _add_head_property(self, obj):
        obj.addProperty("App::PropertyFloat", "head", "gear_parameter",
            "head * modul = additional length of addendum")
        obj.head = 0.0

    def generate_gear_shape(self, fp):
        fp.gear.m = fp.module.Value
        fp.gear.z = fp.teeth
        fp.gear.z1 = fp.inner_diameter.Value
        fp.gear.z2 = fp.outer_diameter.Value
        fp.gear.clearance = fp.clearance
        # check backward compatibility:
        if not "head" in fp.PropertiesList:
            self._add_head_property(fp)
        fp.gear.head = fp.head
        fp.gear.backlash = fp.backlash.Value
        fp.gear._update()

        pts = fp.gear.points(num=fp.numpoints)
        rotated_pts = pts
        rot = rotation(-fp.gear.phipart)
        for i in range(fp.gear.z - 1):
            rotated_pts = list(map(rot, rotated_pts))
            pts.append(np.array([pts[-1][-1], rotated_pts[0][0]]))
            pts += rotated_pts
        pts.append(np.array([pts[-1][-1], pts[0][0]]))
        wi = []
        for i in pts:
            out = BSplineCurve()
            out.interpolate(list(map(fcvec, i)))
            wi.append(out.toShape())
        wi = Wire(wi)
        if fp.height.Value == 0:
            return wi
        elif fp.beta.Value == 0:
            sh = Face(wi)
            return sh.extrude(App.Vector(0, 0, fp.height.Value))
        else:
            return helicalextrusion(
                wi, fp.height.Value, fp.height.Value * np.tan(fp.beta.Value * np.pi / 180) * 2 / fp.gear.d, fp.double_helix)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class BevelGear(BaseGear):

    """parameters:
        pressure_angle:  pressureangle,   10-30°
        pitch_angle:  cone angle,      0 < pitch_angle < pi/4
    """

    def __init__(self, obj):
        super(BevelGear, self).__init__(obj)
        self.bevel_tooth = BevelTooth()
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyAngle", "pitch_angle", "involute_parameter", "pitch_angle")
        obj.addProperty(
            "App::PropertyAngle", "pressure_angle", "involute_parameter", "pressure_angle")
        obj.addProperty("App::PropertyLength", "module", "gear_parameter", "module")
        obj.addProperty(
            "App::PropertyFloat", "clearance", "gear_parameter", "clearance")
        obj.addProperty("App::PropertyInteger", "numpoints",
                        "precision", "number of points for spline")
        obj.addProperty("App::PropertyBool", "reset_origin", "gear_parameter",
                        "if value is true the gears outer face will match the z=0 plane")
        obj.addProperty(
            "App::PropertyLength", "backlash", "gear_parameter", "backlash in mm")
        obj.addProperty("App::PropertyPythonObject",
                        "gear", "gear_paramenter", "test")
        obj.addProperty("App::PropertyAngle", "beta",
                        "gear_paramenter", "test")
        obj.gear = self.bevel_tooth
        obj.module = '1. mm'
        obj.teeth = 15
        obj.pressure_angle = '20. deg'
        obj.pitch_angle = '45. deg'
        obj.height = '5. mm'
        obj.numpoints = 6
        obj.backlash = '0.00 mm'
        obj.clearance = 0.1
        obj.beta = '0 deg'
        obj.reset_origin = True
        self.obj = obj
        obj.Proxy = self

    def generate_gear_shape(self, fp):
        fp.gear.z = fp.teeth
        fp.gear.module = fp.module.Value
        fp.gear.pressure_angle = (90 - fp.pressure_angle.Value) * np.pi / 180.
        fp.gear.pitch_angle = fp.pitch_angle.Value * np.pi / 180
        fp.gear.backlash = fp.backlash.Value
        scale = fp.module.Value * fp.gear.z / 2 / \
            np.tan(fp.pitch_angle.Value * np.pi / 180)
        fp.gear.clearance = fp.clearance / scale
        fp.gear._update()
        pts = list(fp.gear.points(num=fp.numpoints))
        rot = rotation3D(2 * np.pi / fp.teeth)
        # if fp.beta.Value != 0:
        #     pts = [np.array([self.spherical_rot(j, fp.beta.Value * np.pi / 180.) for j in i]) for i in pts]

        rotated_pts = pts
        for i in range(fp.gear.z - 1):
            rotated_pts = list(map(rot, rotated_pts))
            pts.append(np.array([pts[-1][-1], rotated_pts[0][0]]))
            pts += rotated_pts
        pts.append(np.array([pts[-1][-1], pts[0][0]]))
        wires = []
        if not "version" in fp.PropertiesList:
            scale_0 = scale - fp.height.Value / 2
            scale_1 = scale + fp.height.Value / 2
        else: # starting with version 0.0.2
            scale_0 = scale - fp.height.Value
            scale_1 = scale
        if fp.beta.Value == 0:
            wires.append(make_bspline_wire([scale_0 * p for p in pts]))
            wires.append(make_bspline_wire([scale_1 * p for p in pts]))
        else:
            for scale_i in np.linspace(scale_0, scale_1, 20):
                # beta_i = (scale_i - scale_0) * fp.beta.Value * np.pi / 180
                # rot = rotation3D(beta_i)
                # points = [rot(pt) * scale_i for pt in pts]
                angle = fp.beta.Value * np.pi / 180. * \
                    np.sin(np.pi / 4) / \
                    np.sin(fp.pitch_angle.Value * np.pi / 180.)
                points = [np.array([self.spherical_rot(p, angle)
                                    for p in scale_i * pt]) for pt in pts]
                wires.append(make_bspline_wire(points))
        shape = makeLoft(wires, True)
        if fp.reset_origin:
            mat = App.Matrix()
            mat.A33 = -1
            mat.move(fcvec([0, 0, scale_1]))
            shape = shape.transformGeometry(mat)
        return shape
        # return self.create_teeth(pts, pos1, fp.teeth)

    def create_tooth(self):
        w = []
        scal1 = self.obj.m.Value * self.obj.gear.z / 2 / np.tan(
            self.obj.pitch_angle.Value * np.pi / 180) - self.obj.height.Value / 2
        scal2 = self.obj.m.Value * self.obj.gear.z / 2 / np.tan(
            self.obj.pitch_angle.Value * np.pi / 180) + self.obj.height.Value / 2
        s = [scal1, scal2]
        pts = self.obj.gear.points(num=self.obj.numpoints)
        for j, pos in enumerate(s):
            w1 = []

            def scale(x): return fcvec(x * pos)
            for i in pts:
                i_scale = list(map(scale, i))
                w1.append(i_scale)
            w.append(w1)
        surfs = []
        w_t = zip(*w)
        for i in w_t:
            b = BSplineSurface()
            b.interpolate(i)
            surfs.append(b)
        return Shape(surfs)

    def spherical_rot(self, point, phi):
        new_phi = np.sqrt(np.linalg.norm(point)) * phi
        return rotation3D(new_phi)(point)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class WormGear(BaseGear):

    """FreeCAD gear rack"""

    def __init__(self, obj):
        super(WormGear, self).__init__(obj)
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyLength", "module", "gear_parameter", "module")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyLength", 'diameter', "gear_parameter", "diameter")
        obj.addProperty(
            "App::PropertyAngle", "beta", "gear_parameter", "beta ", 1)
        obj.addProperty(
            "App::PropertyAngle", "pressure_angle", "involute_parameter", "pressure angle")
        obj.addProperty(
            "App::PropertyFloat", "head", "gear_parameter", "head * module = additional length of head")
        obj.addProperty(
            "App::PropertyFloat", "clearance", "gear_parameter", "clearance * module = additional length of foot")
        obj.addProperty(
            "App::PropertyBool", "reverse_pitch", "gear_parameter", "reverse rotation of helix")
        obj.teeth = 3
        obj.module = '1. mm'
        obj.pressure_angle = '20. deg'
        obj.height = '5. mm'
        obj.diameter = '5. mm'
        obj.clearance = 0.25
        obj.head = 0
        obj.reverse_pitch = False

        self.obj = obj
        obj.Proxy = self

    def generate_gear_shape(self, fp):
        m = fp.module.Value
        d = fp.diameter.Value
        t = fp.teeth
        h = fp.height

        clearance = fp.clearance
        head = fp.head
        alpha = fp.pressure_angle.Value
        beta = np.arctan(m * t / d)
        fp.beta = np.rad2deg(beta)
        beta = -(fp.reverse_pitch * 2 - 1) * (np.pi / 2 - beta)

        r_1 = (d - (2 + 2 * clearance) * m) / 2
        r_2 = (d + (2 + 2 * head) * m) / 2
        z_a = (2 + head + clearance) * m * np.tan(np.deg2rad(alpha))
        z_b = (m * np.pi - 4 * m * np.tan(np.deg2rad(alpha))) / 2
        z_0 = clearance * m * np.tan(np.deg2rad(alpha))
        z_1 = z_b - z_0
        z_2 = z_1 + z_a
        z_3 = z_2 + z_b - 2 * head * m * np.tan(np.deg2rad(alpha))
        z_4 = z_3 + z_a

        def helical_projection(r, z):
            phi = 2 * z / m / t
            x = r * np.cos(phi)
            y = r * np.sin(phi)
            z = 0 * y
            return np.array([x, y, z]). T

        # create a circle from phi=0 to phi_1 with r_1
        phi_0 = 2 * z_0 / m / t
        phi_1 = 2 * z_1 / m / t
        c1 = Part.makeCircle(r_1, App.Vector(0, 0, 0),
                             App.Vector(0, 0, 1), np.rad2deg(phi_0), np.rad2deg(phi_1))

        # create first bspline
        z_values = np.linspace(z_1, z_2, 10)
        r_values = np.linspace(r_1, r_2, 10)
        points = helical_projection(r_values, z_values)
        bsp1 = Part.BSplineCurve()
        bsp1.interpolate(list(map(fcvec, points)))
        bsp1 = bsp1.toShape()

        # create circle from phi_2 to phi_3
        phi_2 = 2 * z_2 / m / t
        phi_3 = 2 * z_3 / m / t
        c2 = Part.makeCircle(r_2, App.Vector(0, 0, 0), App.Vector(
            0, 0, 1), np.rad2deg(phi_2), np.rad2deg(phi_3))

        # create second bspline
        z_values = np.linspace(z_3, z_4, 10)
        r_values = np.linspace(r_2, r_1, 10)
        points = helical_projection(r_values, z_values)
        bsp2 = Part.BSplineCurve()
        bsp2.interpolate(list(map(fcvec, points)))
        bsp2 = bsp2.toShape()

        wire = Part.Wire([c1, bsp1, c2, bsp2])
        w_all = [wire]

        rot = App.Matrix()
        rot.rotateZ(2 * np.pi / t)
        for i in range(1, t):
            w_all.append(w_all[-1].transformGeometry(rot))

        full_wire = Part.Wire(Part.Wire(w_all))
        if h == 0:
            return full_wire
        else:
            shape = helicalextrusion(full_wire,
                                     h,
                                     h * np.tan(beta) * 2 / d)
            return shape

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ProfileTimingGear(BaseGear):
    """FreeCAD gear rack
       Converted from OpenSCAD https://github.com/rbuckland/openscad.parametric-pulley
    """
    data = {
        "MXL": {
            'pitch': 2.032,
            'offset': 0.254,
            'teeth_depth': 0.508,
            'teeth_width': 1.321,
            'polygon': [[-0.660421,-0.5],[-0.660421,0],[-0.621898,0.006033],[-0.587714,0.023037],[-0.560056,0.049424],[-0.541182,0.083609],[-0.417357,0.424392],[-0.398413,0.458752],[-0.370649,0.48514],[-0.336324,0.502074],[-0.297744,0.508035],[0.297744,0.508035],[0.336268,0.502074],[0.370452,0.48514],[0.39811,0.458752],[0.416983,0.424392],[0.540808,0.083609],[0.559752,0.049424],[0.587516,0.023037],[0.621841,0.006033],[0.660421,0],[0.660421,-0.5]]
        },
        "40 D.P.": {
            'pitch': 2.07264,
            'offset': 0.1778,
            'teeth_depth': 0.457,
            'teeth_width': 1.226,
            'polygon': [[-0.612775,-0.5],[-0.612775,0],[-0.574719,0.010187],[-0.546453,0.0381],[-0.355953,0.3683],[-0.327604,0.405408],[-0.291086,0.433388],[-0.248548,0.451049],[-0.202142,0.4572],[0.202494,0.4572],[0.248653,0.451049],[0.291042,0.433388],[0.327609,0.405408],[0.356306,0.3683],[0.546806,0.0381],[0.574499,0.010187],[0.612775,0],[0.612775,-0.5]]
        },
        "XL": {
            'pitch': 5.08,
            'offset': 0.254,
            'teeth_depth': 1.27,
            'teeth_width': 3.051,
            'polygon': [[-1.525411,-1],[-1.525411,0],[-1.41777,0.015495],[-1.320712,0.059664],[-1.239661,0.129034],[-1.180042,0.220133],[-0.793044,1.050219],[-0.733574,1.141021],[-0.652507,1.210425],[-0.555366,1.254759],[-0.447675,1.270353],[0.447675,1.270353],[0.555366,1.254759],[0.652507,1.210425],[0.733574,1.141021],[0.793044,1.050219],[1.180042,0.220133],[1.239711,0.129034],[1.320844,0.059664],[1.417919,0.015495],[1.525411,0],[1.525411,-1]]
        },
        "H": {
            'pitch': 9.525,
            'offset': 0.381,
            'teeth_depth': 1.905,
            'teeth_width': 5.359,
            'polygon': [[-2.6797,-1],[-2.6797,0],[-2.600907,0.006138],[-2.525342,0.024024],[-2.45412,0.052881],[-2.388351,0.091909],[-2.329145,0.140328],[-2.277614,0.197358],[-2.234875,0.262205],[-2.202032,0.334091],[-1.75224,1.57093],[-1.719538,1.642815],[-1.676883,1.707663],[-1.62542,1.764693],[-1.566256,1.813112],[-1.500512,1.85214],[-1.4293,1.880997],[-1.353742,1.898883],[-1.274949,1.905021],[1.275281,1.905021],[1.354056,1.898883],[1.429576,1.880997],[1.500731,1.85214],[1.566411,1.813112],[1.625508,1.764693],[1.676919,1.707663],[1.719531,1.642815],[1.752233,1.57093],[2.20273,0.334091],[2.235433,0.262205],[2.278045,0.197358],[2.329455,0.140328],[2.388553,0.091909],[2.454233,0.052881],[2.525384,0.024024],[2.600904,0.006138],[2.6797,0],[2.6797,-1]]
        },
        "T2.5": {
            'b': 0.7467,
            'c': 0.796,
            'd': 1.026,
            'teeth_depth': 0.7,
            'teeth_width': 1.678,
            'polygon': [[-0.839258,-0.5],[-0.839258,0],[-0.770246,0.021652],[-0.726369,0.079022],[-0.529167,0.620889],[-0.485025,0.67826],[-0.416278,0.699911],[0.416278,0.699911],[0.484849,0.67826],[0.528814,0.620889],[0.726369,0.079022],[0.770114,0.021652],[0.839258,0],[0.839258,-0.5]]
        },
        "T5": {
            'b': 0.6523,
            'c': 1.591,
            'd': 1.064,
            'teeth_depth': 1.19,
            'teeth_width': 3.264,
            'polygon': [[-1.632126,-0.5],[-1.632126,0],[-1.568549,0.004939],[-1.507539,0.019367],[-1.450023,0.042686],[-1.396912,0.074224],[-1.349125,0.113379],[-1.307581,0.159508],[-1.273186,0.211991],[-1.246868,0.270192],[-1.009802,0.920362],[-0.983414,0.978433],[-0.949018,1.030788],[-0.907524,1.076798],[-0.859829,1.115847],[-0.80682,1.147314],[-0.749402,1.170562],[-0.688471,1.184956],[-0.624921,1.189895],[0.624971,1.189895],[0.688622,1.184956],[0.749607,1.170562],[0.807043,1.147314],[0.860055,1.115847],[0.907754,1.076798],[0.949269,1.030788],[0.9837,0.978433],[1.010193,0.920362],[1.246907,0.270192],[1.273295,0.211991],[1.307726,0.159508],[1.349276,0.113379],[1.397039,0.074224],[1.450111,0.042686],[1.507589,0.019367],[1.568563,0.004939],[1.632126,0],[1.632126,-0.5]]
        },
        "T10": {
            'pitch': 10,
            'offset': 0.93,
            'teeth_depth': 2.5,
            'teeth_width': 6.13,
            'polygon': [[-3.06511,-1],[-3.06511,0],[-2.971998,0.007239],[-2.882718,0.028344],[-2.79859,0.062396],[-2.720931,0.108479],[-2.651061,0.165675],[-2.590298,0.233065],[-2.539962,0.309732],[-2.501371,0.394759],[-1.879071,2.105025],[-1.840363,2.190052],[-1.789939,2.266719],[-1.729114,2.334109],[-1.659202,2.391304],[-1.581518,2.437387],[-1.497376,2.47144],[-1.408092,2.492545],[-1.314979,2.499784],[1.314979,2.499784],[1.408091,2.492545],[1.497371,2.47144],[1.581499,2.437387],[1.659158,2.391304],[1.729028,2.334109],[1.789791,2.266719],[1.840127,2.190052],[1.878718,2.105025],[2.501018,0.394759],[2.539726,0.309732],[2.59015,0.233065],[2.650975,0.165675],[2.720887,0.108479],[2.798571,0.062396],[2.882713,0.028344],[2.971997,0.007239],[3.06511,0],[3.06511,-1]]
        },
        "AT5": {
            'b': 0.6523,
            'c': 1.591,
            'd': 1.064,
            'teeth_depth': 1.19,
            'teeth_width': 4.268,
            'polygon': [[-2.134129,-0.75],[-2.134129,0],[-2.058023,0.005488],[-1.984595,0.021547],[-1.914806,0.047569],[-1.849614,0.082947],[-1.789978,0.127073],[-1.736857,0.179338],[-1.691211,0.239136],[-1.653999,0.305859],[-1.349199,0.959203],[-1.286933,1.054635],[-1.201914,1.127346],[-1.099961,1.173664],[-0.986896,1.18992],[0.986543,1.18992],[1.099614,1.173664],[1.201605,1.127346],[1.286729,1.054635],[1.349199,0.959203],[1.653646,0.305859],[1.690859,0.239136],[1.73651,0.179338],[1.789644,0.127073],[1.849305,0.082947],[1.914539,0.047569],[1.984392,0.021547],[2.057906,0.005488],[2.134129,0],[2.134129,-0.75]]
        },
        "HTD3M":  {
            'pitch': 3.0,
            'offset': 0.381,
            'teeth_depth': 1.289,
            'teeth_width': 2.27,
            'polygon': [[-1.135062,-0.5],[-1.135062,0],[-1.048323,0.015484],[-0.974284,0.058517],[-0.919162,0.123974],[-0.889176,0.206728],[-0.81721,0.579614],[-0.800806,0.653232],[-0.778384,0.72416],[-0.750244,0.792137],[-0.716685,0.856903],[-0.678005,0.918199],[-0.634505,0.975764],[-0.586483,1.029338],[-0.534238,1.078662],[-0.47807,1.123476],[-0.418278,1.16352],[-0.355162,1.198533],[-0.289019,1.228257],[-0.22015,1.25243],[-0.148854,1.270793],[-0.07543,1.283087],[-0.000176,1.28905],[0.075081,1.283145],[0.148515,1.270895],[0.219827,1.252561],[0.288716,1.228406],[0.354879,1.19869],[0.418018,1.163675],[0.477831,1.123623],[0.534017,1.078795],[0.586276,1.029452],[0.634307,0.975857],[0.677809,0.91827],[0.716481,0.856953],[0.750022,0.792167],[0.778133,0.724174],[0.800511,0.653236],[0.816857,0.579614],[0.888471,0.206728],[0.919014,0.123974],[0.974328,0.058517],[1.048362,0.015484],[1.135062,0],[1.135062,-0.5]]
         },
        "HTD5M":  {
            'pitch': 5.0,
            'offset': 0.5715,
            'teeth_depth': 2.199,
            'teeth_width': 3.781,
            'polygon': [[-1.89036,-0.75],[-1.89036,0],[-1.741168,0.02669],[-1.61387,0.100806],[-1.518984,0.21342],[-1.467026,0.3556],[-1.427162,0.960967],[-1.398568,1.089602],[-1.359437,1.213531],[-1.310296,1.332296],[-1.251672,1.445441],[-1.184092,1.552509],[-1.108081,1.653042],[-1.024167,1.746585],[-0.932877,1.832681],[-0.834736,1.910872],[-0.730271,1.980701],[-0.62001,2.041713],[-0.504478,2.09345],[-0.384202,2.135455],[-0.259708,2.167271],[-0.131524,2.188443],[-0.000176,2.198511],[0.131296,2.188504],[0.259588,2.167387],[0.384174,2.135616],[0.504527,2.093648],[0.620123,2.04194],[0.730433,1.980949],[0.834934,1.911132],[0.933097,1.832945],[1.024398,1.746846],[1.108311,1.653291],[1.184308,1.552736],[1.251865,1.445639],[1.310455,1.332457],[1.359552,1.213647],[1.39863,1.089664],[1.427162,0.960967],[1.467026,0.3556],[1.518984,0.21342],[1.61387,0.100806],[1.741168,0.02669],[1.89036,0],[1.89036,-0.75]]
         },
        "HTD8M": {
            'pitch': 8,
            'offset': 0.6858,
            'teeth_depth': 3.607,
            'teeth_width': 6.603,
            'polygon': [[-3.301471,-1],[-3.301471,0],[-3.16611,0.012093],[-3.038062,0.047068],[-2.919646,0.10297],[-2.813182,0.177844],[-2.720989,0.269734],[-2.645387,0.376684],[-2.588694,0.496739],[-2.553229,0.627944],[-2.460801,1.470025],[-2.411413,1.691917],[-2.343887,1.905691],[-2.259126,2.110563],[-2.158035,2.30575],[-2.041518,2.490467],[-1.910478,2.66393],[-1.76582,2.825356],[-1.608446,2.973961],[-1.439261,3.10896],[-1.259169,3.22957],[-1.069074,3.335006],[-0.869878,3.424485],[-0.662487,3.497224],[-0.447804,3.552437],[-0.226732,3.589341],[-0.000176,3.607153],[0.226511,3.589461],[0.447712,3.552654],[0.66252,3.497516],[0.870027,3.424833],[1.069329,3.33539],[1.259517,3.229973],[1.439687,3.109367],[1.608931,2.974358],[1.766344,2.825731],[1.911018,2.664271],[2.042047,2.490765],[2.158526,2.305998],[2.259547,2.110755],[2.344204,1.905821],[2.411591,1.691983],[2.460801,1.470025],[2.553229,0.627944],[2.588592,0.496739],[2.645238,0.376684],[2.720834,0.269734],[2.81305,0.177844],[2.919553,0.10297],[3.038012,0.047068],[3.166095,0.012093],[3.301471,0],[3.301471,-1]]
        },
        "GT2 2MM": {
            'pitch': 2.0,
            'offset': 0.254,
            'teeth_depth': 0.764,
            'teeth_width': 1.494,
            'polygon': [[0.747183,-0.5],[0.747183,0],[0.647876,0.037218],[0.598311,0.130528],[0.578556,0.238423],[0.547158,0.343077],[0.504649,0.443762],[0.451556,0.53975],[0.358229,0.636924],[0.2484,0.707276],[0.127259,0.750044],[0,0.76447],[-0.127259,0.750044],[-0.2484,0.707276],[-0.358229,0.636924],[-0.451556,0.53975],[-0.504797,0.443762],[-0.547291,0.343077],[-0.578605,0.238423],[-0.598311,0.130528],[-0.648009,0.037218],[-0.747183,0],[-0.747183,-0.5]]
        },
        "GT2 3MM": {
            'pitch': 3.0,
            'offset': 0.381,
            'teeth_depth': 1.169,
            'teeth_width': 2.31,
            'polygon': [[-1.155171,-0.5],[-1.155171,0],[-1.065317,0.016448],[-0.989057,0.062001],[-0.93297,0.130969],[-0.90364,0.217664],[-0.863705,0.408181],[-0.800056,0.591388],[-0.713587,0.765004],[-0.60519,0.926747],[-0.469751,1.032548],[-0.320719,1.108119],[-0.162625,1.153462],[0,1.168577],[0.162625,1.153462],[0.320719,1.108119],[0.469751,1.032548],[0.60519,0.926747],[0.713587,0.765004],[0.800056,0.591388],[0.863705,0.408181],[0.90364,0.217664],[0.932921,0.130969],[0.988924,0.062001],[1.065168,0.016448],[1.155171,0],[1.155171,-0.5]]
        },
        "GT2 5MM": {
            'pitch': 5.0,
            'offset': 0.571,
            'teeth_depth': 1.969,
            'teeth_width': 3.952,
            'polygon': [[-1.975908,-0.75],[-1.975908,0],[-1.797959,0.03212],[-1.646634,0.121224],[-1.534534,0.256431],[-1.474258,0.426861],[-1.446911,0.570808],[-1.411774,0.712722],[-1.368964,0.852287],[-1.318597,0.989189],[-1.260788,1.123115],[-1.195654,1.25375],[-1.12331,1.380781],[-1.043869,1.503892],[-0.935264,1.612278],[-0.817959,1.706414],[-0.693181,1.786237],[-0.562151,1.851687],[-0.426095,1.9027],[-0.286235,1.939214],[-0.143795,1.961168],[0,1.9685],[0.143796,1.961168],[0.286235,1.939214],[0.426095,1.9027],[0.562151,1.851687],[0.693181,1.786237],[0.817959,1.706414],[0.935263,1.612278],[1.043869,1.503892],[1.123207,1.380781],[1.195509,1.25375],[1.26065,1.123115],[1.318507,0.989189],[1.368956,0.852287],[1.411872,0.712722],[1.447132,0.570808],[1.474611,0.426861],[1.534583,0.256431],[1.646678,0.121223],[1.798064,0.03212],[1.975908,0],[1.975908,-0.75]]
        }
    }

    def __init__(self, obj):
        super(ProfileTimingGear, self).__init__(obj)
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyEnumeration", "type", "gear_parameter", "type of timing-gear")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyLength", "additional_teeth_width", "gear_parameter", "additional teeth width for better fit")
        obj.addProperty(
            "App::PropertyLength", "pitch", "computed", "pitch off gear", 1)
        obj.addProperty(
            "App::PropertyLength", "offset", "computed", "pitch line offset (belt thickness)", 1)
        obj.addProperty(
            "App::PropertyLength", "teeth_width", "computed", "teeth width", 1)
        obj.addProperty(
            "App::PropertyLength", "teeth_radius", "computed", "teeth radius (including addtional width)", 1)
        obj.addProperty(
            "App::PropertyLength", "teeth_depth", "computed", "teeth depth", 1)

        obj.addProperty(
            "App::PropertyLength", "od", "computed", "outer diameter", 1)
        obj.addProperty(
            "App::PropertyLength", "radius", "computed", "outer diameter", 1)
        obj.teeth = 24
        obj.type = ['HTD5M', 'HTD3M', 'HTD8M', 'MXL', '40 D.P.', 'XL', 'H', 'T2.5', 'T5', 'T10', 'AT5', 'GT2 2MM', 'GT2 3MM', 'GT2 5MM']
        obj.height = '9.3 mm'
        obj.additional_teeth_width = 0.2

        self.obj = obj
        obj.Proxy = self

    def generate_gear_shape(self, fp):
        tp = fp.type
        teeth = fp.teeth
        gt_data = self.data[tp]
        if 'pitch' in gt_data:
            pitch = fp.pitch = gt_data['pitch']
            offset = fp.offset = gt_data['offset']   # belt thickness
            od = fp.od = 2 * ((teeth * pitch)/(math.pi * 2)-offset)
        else:  # use curvefit to calc od.
            b = gt_data['b']
            c = gt_data['c']
            d = gt_data['d']
            od = fp.od = ((c * math.pow(teeth,d)) / (b + math.pow(teeth,d))) * teeth
        radius = fp.radius = od / 2
        polygon = gt_data['polygon']
        teeth_width = fp.teeth_width= gt_data['teeth_width']
        teeth_depth = fp.teeth_depth = gt_data['teeth_depth']
        teeth_radius = fp.teeth_radius = (teeth_width + fp.additional_teeth_width.Value) / 2.0
        teeth_distance_from_center = math.sqrt(math.pow(radius, 2) - math.pow(teeth_radius,2))
        teeth_scale = teeth_width / (teeth_width + fp.additional_teeth_width.Value)

        polygon = [(x * teeth_scale, y) for x, y in polygon]
        polygon = [(x, y - teeth_distance_from_center) for x, y in polygon]

        last = polygon[-1]
        lines = []
        for pt in polygon:
          line = Part.LineSegment()
          line.StartPoint = (last[0], last[1], 0)
          line.EndPoint = (pt[0], pt[1], 0)
          lines.append(line.toShape())
          last = pt

        wire = Part.Wire(lines)

        circle = Part.Circle()
        circle.Radius = radius
        gear = Part.Face(Part.Wire(circle.toShape()))
        gear = gear.cut(Part.Face(wire))
        rot = App.Matrix()
        for _ in range(fp.teeth - 1):
            rot.rotateZ(np.pi * 2 / fp.teeth)
            gear = gear.cut(Part.Face(wire.transformGeometry(rot)))

        if fp.height.Value == 0:
            return gear
        else:
            return gear.extrude(App.Vector(0, 0, fp.height))

    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass


class TimingGear(BaseGear):

    """FreeCAD gear rack"""
    data = {"gt2":  {'pitch': 2.0, 'u': 0.254,  'h': 0.75,
                    'H': 1.38,    'r0': 0.555, 'r1': 1.0,
                    'rs': 0.15,   'offset': 0.40
                    },
            "gt3":  {'pitch': 3.0, 'u': 0.381, 'h': 1.14,
                    'H': 2.40, 'r0': 0.85, 'r1': 1.52,
                    'rs': 0.25, 'offset': 0.61
                    },
            "gt5":  {
                    'pitch': 5.0,  'u': 0.5715,  'h': 1.93,
                    'H': 3.81,  'r0': 1.44,  'r1': 2.57,
                    'rs': 0.416,  'offset': 1.03
                    }
            }

    def __init__(self, obj):
        super(TimingGear, self).__init__(obj)
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyEnumeration", "type", "gear_parameter", "type of timing-gear")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty(
            "App::PropertyLength", "pitch", "computed", "pitch off gear", 1)
        obj.addProperty(
            "App::PropertyLength", "h", "computed", "radial height of teeth", 1)
        obj.addProperty(
            "App::PropertyLength", "u", "computed", "radial difference between pitch \
            diameter and head of gear", 1)
        obj.addProperty(
            "App::PropertyLength", "r0", "computed", "radius of first arc", 1)
        obj.addProperty(
            "App::PropertyLength", "r1", "computed", "radius of second arc", 1)
        obj.addProperty(
            "App::PropertyLength", "rs", "computed", "radius of third arc", 1)
        obj.addProperty(
            "App::PropertyLength", "offset", "computed", "x-offset of second arc-midpoint", 1)
        obj.teeth = 15
        obj.type = ['gt2', 'gt3', 'gt5']
        obj.height = '5. mm'

        self.obj = obj
        obj.Proxy = self

    def generate_gear_shape(self, fp):
        # m ... center of arc/circle
        # r ... radius of arc/circle
        # x ... end-point of arc
        # phi ... angle
        tp = fp.type
        gt_data = self.data[tp]
        pitch = fp.pitch = gt_data["pitch"]
        h = fp.h = gt_data["h"]
        u = fp.u = gt_data["u"]
        r_12 = fp.r0 = gt_data["r0"]
        r_23 = fp.r1 = gt_data["r1"]
        r_34 = fp.rs = gt_data["rs"]
        offset = fp.offset = gt_data["offset"]

        phi_12 = np.arctan(np.sqrt(1. / (((r_12 - r_23) / offset) ** 2 - 1)))
        rp = pitch * fp.teeth / np.pi / 2.
        r4 = r5 = rp - u

        m_12 = np.array([0., r5 - h + r_12])
        m_23 = np.array([offset, offset / np.tan(phi_12) + m_12[1]])
        m_23y = m_23[1]

        # solving for phi4:
        # sympy.solve(
        # ((r5 - r_34) * sin(phi4) + offset) ** 2 + \
        # ((r5 - r_34) * cos(phi4) - m_23y) ** 2 - \
        # ((r_34 + r_23) ** 2), phi4)

        
        phi4 = 2*np.arctan((-2*offset*r5 + 2*offset*r_34 + np.sqrt(-m_23y**4 - 2*m_23y**2*offset**2 + \
        2*m_23y**2*r5**2 - 4*m_23y**2*r5*r_34 + 2*m_23y**2*r_23**2 + \
        4*m_23y**2*r_23*r_34 + 4*m_23y**2*r_34**2 - offset**4 + 2*offset**2*r5**2 - \
        4*offset**2*r5*r_34 + 2*offset**2*r_23**2 + 4*offset**2*r_23*r_34 + 4*offset**2*r_34**2 - \
        r5**4 + 4*r5**3*r_34 + 2*r5**2*r_23**2 + 4*r5**2*r_23*r_34 - \
        4*r5**2*r_34**2 - 4*r5*r_23**2*r_34 - 8*r5*r_23*r_34**2 - r_23**4 - \
        4*r_23**3*r_34 - 4*r_23**2*r_34**2))/(m_23y**2 + 2*m_23y*r5 - \
        2*m_23y*r_34 + offset**2 + r5**2 - 2*r5*r_34 - r_23**2 - 2*r_23*r_34))

        phi5 = np.pi / fp.teeth


        m_34 = (r5 - r_34) * np.array([-np.sin(phi4), np.cos(phi4)])


        x2 = np.array([-r_12 * np.sin(phi_12), m_12[1] - r_12 * np.cos(phi_12)])
        x3 = m_34 + r_34 / (r_34 + r_23) * (m_23 - m_34)
        x4 = r4 * np.array([-np.sin(phi4), np.cos(phi4)])


        ref = reflection(-phi5 - np.pi / 2)
        x6 = ref(x4)
        mir = np.array([-1., 1.])
        xn2 = mir * x2
        xn3 = mir * x3
        xn4 = mir * x4

        mn_34 = mir * m_34
        mn_23 = mir * m_23


        arc_1 = part_arc_from_points_and_center(xn4, xn3, mn_34).toShape()
        arc_2 = part_arc_from_points_and_center(xn3, xn2, mn_23).toShape()
        arc_3 = part_arc_from_points_and_center(xn2, x2, m_12).toShape()
        arc_4 = part_arc_from_points_and_center(x2, x3, m_23).toShape()
        arc_5 = part_arc_from_points_and_center(x3, x4, m_34).toShape()
        arc_6 = part_arc_from_points_and_center(x4, x6, np.array([0. ,0.])).toShape()

        wire = Part.Wire([arc_1, arc_2, arc_3, arc_4, arc_5, arc_6])
        wires = [wire]
        rot = App.Matrix()
        rot.rotateZ(np.pi * 2 / fp.teeth)
        for _ in range(fp.teeth - 1):
            wire = wire.transformGeometry(rot)
            wires.append(wire)

        wi = Part.Wire(wires)
        if fp.height.Value == 0:
            return wi
        else:
            return Part.Face(wi).extrude(App.Vector(0, 0, fp.height))

    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass


class LanternGear(BaseGear):
    def __init__(self, obj):
        super(LanternGear, self).__init__(obj)
        obj.addProperty("App::PropertyInteger",
                        "teeth", "gear_parameter", "number of teeth")
        obj.addProperty(
            "App::PropertyLength", "module", "gear_parameter", "module")
        obj.addProperty(
            "App::PropertyLength", "bolt_radius", "gear_parameter", "the bolt radius of the rack/chain")
        obj.addProperty(
            "App::PropertyLength", "height", "gear_parameter", "height")
        obj.addProperty("App::PropertyInteger",
                        "num_profiles", "accuracy", "number of profiles used for loft")
        obj.addProperty(
            "App::PropertyFloat", "head", "gear_parameter", "head * module = additional length of head")

        obj.teeth = 15
        obj.module = '1. mm'
        obj.bolt_radius = '1 mm'
        
        obj.height = '5. mm'
        obj.num_profiles = 10
        
        self.obj = obj
        obj.Proxy = self

    def generate_gear_shape(self, fp):
        m = fp.module.Value
        teeth = fp.teeth
        r_r = fp.bolt_radius.Value
        r_0 = m * teeth / 2
        r_max = r_0 + r_r + fp.head * m

        phi_max = (r_r + np.sqrt(r_max**2 - r_0**2)) / r_0

        def find_phi_min(phi_min):
            return r_0*(phi_min**2*r_0 - 2*phi_min*r_0*np.sin(phi_min) - \
                   2*phi_min*r_r - 2*r_0*np.cos(phi_min) + 2*r_0 + 2*r_r*np.sin(phi_min))
        try:
            import scipy.optimize
            phi_min = scipy.optimize.root(find_phi_min, (phi_max + r_r / r_0 * 4) / 5).x[0] # , r_r / r_0, phi_max)
        except ImportError:
            App.Console.PrintWarning("scipy not available. Can't compute numerical root. Leads to a wrong bolt-radius")
            phi_min = r_r / r_0

        # phi_min = 0 # r_r / r_0
        phi = np.linspace(phi_min, phi_max, fp.num_profiles)
        x = r_0 * (np.cos(phi) + phi * np.sin(phi)) - r_r * np.sin(phi)
        y = r_0 * (np.sin(phi) - phi * np.cos(phi)) + r_r * np.cos(phi)
        xy1 = np.array([x, y]).T
        p_1 = xy1[0]
        p_1_end = xy1[-1]
        bsp_1 = BSplineCurve()
        bsp_1.interpolate(list(map(fcvec, xy1)))
        w_1 = bsp_1.toShape()

        xy2 = xy1 * np.array([1., -1.])
        p_2 = xy2[0]
        p_2_end = xy2[-1]
        bsp_2 = BSplineCurve()
        bsp_2.interpolate(list(map(fcvec, xy2)))
        w_2 = bsp_2.toShape()

        p_12 = np.array([r_0 - r_r, 0.])

        arc = Part.Arc(App.Vector(*p_1, 0.), App.Vector(*p_12, 0.), App.Vector(*p_2, 0.)).toShape()

        rot = rotation(-np.pi * 2 / teeth)
        p_3 = rot(np.array([p_2_end]))[0]
        # l = Part.LineSegment(fcvec(p_1_end), fcvec(p_3)).toShape()
        l = part_arc_from_points_and_center(p_1_end, p_3, np.array([0., 0.])).toShape()
        w = Part.Wire([w_2, arc, w_1, l])
        wires = [w]

        rot = App.Matrix()
        for _ in range(teeth - 1):
            rot.rotateZ(np.pi * 2 / teeth)
            wires.append(w.transformGeometry(rot))

        wi = Part.Wire(wires)
        if fp.height.Value == 0:
            return wi
        else:
            return Part.Face(wi).extrude(App.Vector(0, 0, fp.height))

    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass

class HypoCycloidGear(BaseGear):

    """parameters:
        pressure_angle:  pressureangle,   10-30°
        pitch_angle:  cone angle,      0 < pitch_angle < pi/4
    """

    def __init__(self, obj):
        super(HypoCycloidGear, self).__init__(obj)
        obj.addProperty("App::PropertyFloat","pin_circle_radius",       "gear_parameter","Pin ball circle radius(overrides Tooth Pitch")
        obj.addProperty("App::PropertyFloat","roller_diameter",         "gear_parameter","Roller Diameter")
        obj.addProperty("App::PropertyFloat","eccentricity",            "gear_parameter","Eccentricity")
        obj.addProperty("App::PropertyAngle","pressure_angle_lim",      "gear_parameter","Pressure angle limit")
        obj.addProperty("App::PropertyFloat","pressure_angle_offset",   "gear_parameter","Offset in pressure angle")
        obj.addProperty("App::PropertyInteger","teeth_number",          "gear_parameter","Number of teeth in Cam")
        obj.addProperty("App::PropertyInteger","segment_count",         "gear_parameter","Number of points used for spline interpolation")
        obj.addProperty("App::PropertyLength","hole_radius",            "gear_parameter","Center hole's radius")


        obj.addProperty("App::PropertyBool", "show_pins", "Pins", "Create pins in place")
        obj.addProperty("App::PropertyLength","pin_height", "Pins", "height")
        obj.addProperty("App::PropertyBool", "center_pins", "Pins", "Center pin Z axis to generated disks")

        obj.addProperty("App::PropertyBool", "show_disk0", "Disks", "Show main cam disk")
        obj.addProperty("App::PropertyBool", "show_disk1", "Disks", "Show another reversed cam disk on top")
        obj.addProperty("App::PropertyLength","disk_height", "Disks", "height")

        obj.pin_circle_radius = 66
        obj.roller_diameter = 3
        obj.eccentricity = 1.5
        obj.pressure_angle_lim = '50.0 deg'
        obj.pressure_angle_offset = 0.01
        obj.teeth_number = 42
        obj.segment_count = 42
        obj.hole_radius = '30. mm'

        obj.show_pins  = True
        obj.pin_height = '20. mm'
        obj.center_pins= True

        obj.show_disk0 = True
        obj.show_disk1 = True
        obj.disk_height= '10. mm'

        self.obj = obj
        obj.Proxy = self

    def to_polar(self,x, y):
        return (x**2 + y**2)**0.5, math.atan2(y, x)

    def to_rect(self,r, a):
        return r*math.cos(a), r*math.sin(a)

    def calcyp(self,p,a,e,n):
        return math.atan(math.sin(n*a)/(math.cos(n*a)+(n*p)/(e*(n+1))))

    def calc_x(self,p,d,e,n,a):
        return (n*p)*math.cos(a)+e*math.cos((n+1)*a)-d/2*math.cos(self.calcyp(p,a,e,n)+a)

    def calc_y(self,p,d,e,n,a):
        return (n*p)*math.sin(a)+e*math.sin((n+1)*a)-d/2*math.sin(self.calcyp(p,a,e,n)+a)

    def calc_pressure_angle(self,p,d,n,a):
        ex = 2**0.5
        r3 = p*n
        rg = r3/ex
        pp = rg * (ex**2 + 1 - 2*ex*math.cos(a))**0.5 - d/2
        return math.asin( (r3*math.cos(a)-rg)/(pp+d/2))*180/math.pi

    def calc_pressure_limit(self,p,d,e,n,a):
        ex = 2**0.5
        r3 = p*n
        rg = r3/ex
        q = (r3**2 + rg**2 - 2*r3*rg*math.cos(a))**0.5
        x = rg - e + (q-d/2)*(r3*math.cos(a)-rg)/q
        y = (q-d/2)*r3*math.sin(a)/q
        return (x**2 + y**2)**0.5

    def check_limit(self,x,y,maxrad,minrad,offset):
        r, a = self.to_polar(x, y)
        if (r > maxrad) or (r < minrad):
                r = r - offset
                x, y = self.to_rect(r, a)
        return x, y

    def generate_gear_shape(self, fp):
        b = fp.pin_circle_radius
        d = fp.roller_diameter
        e = fp.eccentricity
        n = fp.teeth_number
        p = b/n
        s = fp.segment_count
        ang = fp.pressure_angle_lim
        c = fp.pressure_angle_offset

        q = 2*math.pi/float(s)

        # Find the pressure angle limit circles
        minAngle = -1.0
        maxAngle = -1.0
        for i in range(0, 180):
            x = self.calc_pressure_angle(p, d, n, i * math.pi / 180.)
            if ( x < ang) and (minAngle < 0):
                minAngle = float(i)
            if (x < -ang) and (maxAngle < 0):
                maxAngle = float(i-1)

        minRadius = self.calc_pressure_limit(p, d, e, n, minAngle * math.pi / 180.)
        maxRadius = self.calc_pressure_limit(p, d, e, n, maxAngle * math.pi / 180.)
        # unused
        # Wire(Part.makeCircle(minRadius,App.Vector(-e, 0, 0)))
        # Wire(Part.makeCircle(maxRadius,App.Vector(-e, 0, 0)))

        App.Console.PrintMessage("Generating cam disk\r\n")
        #generate the cam profile - note: shifted in -x by eccentricicy amount
        i=0
        x = self.calc_x(p, d, e, n, q*i / float(n))
        y = self.calc_y(p, d, e, n, q*i / n)
        x, y = self.check_limit(x,y,maxRadius,minRadius,c)
        points = [App.Vector(x-e, y, 0)]
        for i in range(0,s):
            x = self.calc_x(p, d, e, n, q*(i+1) / n)
            y = self.calc_y(p, d, e, n, q*(i+1) / n)
            x, y = self.check_limit(x, y, maxRadius, minRadius, c)
            points.append([x-e, y, 0])

        wi = make_bspline_wire([points])
        wires = []
        mat= App.Matrix()
        mat.move(App.Vector(e, 0., 0.))
        mat.rotateZ(2 * np.pi / n)
        mat.move(App.Vector(-e, 0., 0.))
        for _ in range(n):
            wi = wi.transformGeometry(mat)
            wires.append(wi)

        cam = Face(Wire(wires))
        #add a circle in the center of the cam
        if fp.hole_radius.Value:
            centerCircle = Face(Wire(Part.makeCircle(fp.hole_radius.Value, App.Vector(-e, 0, 0))))
            cam = cam.cut(centerCircle)

        to_be_fused = []
        if fp.show_disk0==True:
            if fp.disk_height.Value==0:
                to_be_fused.append(cam)
            else:
                to_be_fused.append(cam.extrude(App.Vector(0, 0, fp.disk_height.Value)))

        #secondary cam disk
        if fp.show_disk1==True:
            App.Console.PrintMessage("Generating secondary cam disk\r\n")
            second_cam = cam.copy()
            mat= App.Matrix()
            mat.rotateZ(np.pi)
            mat.move(App.Vector(-e, 0, 0))
            if n%2 == 0:
                mat.rotateZ(np.pi/n)
            mat.move(App.Vector(e, 0, 0))
            second_cam = second_cam.transformGeometry(mat)
            if fp.disk_height.Value==0:
                to_be_fused.append(second_cam)
            else:
                to_be_fused.append(second_cam.extrude(App.Vector(0, 0, -fp.disk_height.Value)))

        #pins
        if fp.show_pins==True:
            App.Console.PrintMessage("Generating pins\r\n")
            pins = []
            for i in range(0, n + 1):
                x = p * n * math.cos(2 * math.pi / (n + 1) * i)
                y = p * n * math.sin(2 * math.pi / (n + 1) * i)
                pins.append(Wire(Part.makeCircle(d / 2, App.Vector(x, y, 0))))

            pins = Face(pins)

            z_offset = -fp.pin_height.Value / 2;

            if fp.center_pins==True:
                if fp.show_disk0==True and fp.show_disk1==False:
                    z_offset += fp.disk_height.Value / 2;
                elif fp.show_disk0==False and fp.show_disk1==True:
                    z_offset += -fp.disk_height.Value / 2;
            #extrude
            if z_offset!=0:
                pins.translate(App.Vector(0, 0, z_offset))
            if fp.pin_height!=0:
                pins = pins.extrude(App.Vector(0, 0, fp.pin_height.Value))

            to_be_fused.append(pins);

        if to_be_fused:
            return Part.makeCompound(to_be_fused)

    def __getstate__(self):
        pass

    def __setstate__(self, state):
        pass

def part_arc_from_points_and_center(p_1, p_2, m):
    p_1, p_12, p_2 = arc_from_points_and_center(p_1, p_2, m)
    return Part.Arc(App.Vector(*p_1, 0.), App.Vector(*p_12, 0.), App.Vector(*p_2, 0.))


def helicalextrusion(wire, height, angle, double_helix=False):
    direction = bool(angle < 0)
    if double_helix:
        first_spine = makeHelix(height * 2. * np.pi /
                                abs(angle), 0.5 * height, 10., 0, direction)
        first_solid = first_spine.makePipeShell([wire], True, True)
        second_solid = first_solid.mirror(
            fcvec([0., 0., 0.]), fcvec([0, 0, 1]))
        faces = first_solid.Faces + second_solid.Faces
        faces = [f for f in faces if not on_mirror_plane(
            f, 0., fcvec([0., 0., 1.]))]
        solid = makeSolid(makeShell(faces))
        mat = App.Matrix()
        mat.move(fcvec([0, 0, 0.5 * height]))
        return solid.transformGeometry(mat)
    else:
        first_spine = makeHelix(height * 2 * np.pi /
                                abs(angle), height, 10., 0, direction)
        first_solid = first_spine.makePipeShell([wire], True, True)
        return first_solid


def make_face(edge1, edge2):
    v1, v2 = edge1.Vertexes
    v3, v4 = edge2.Vertexes
    e1 = Wire(edge1)
    e2 = Line(v1.Point, v3.Point).toShape().Edges[0]
    e3 = edge2
    e4 = Line(v4.Point, v2.Point).toShape().Edges[0]
    w = Wire([e3, e4, e1, e2])
    return(Face(w))


def make_bspline_wire(pts):
    wi = []
    for i in pts:
        out = BSplineCurve()
        out.interpolate(list(map(fcvec, i)))
        wi.append(out.toShape())
    return Wire(wi)


def on_mirror_plane(face, z, direction, small_size=0.000001):
    # the tolerance is very high. Maybe there is a bug in Part.makeHelix.
    return (face.normalAt(0, 0).cross(direction).Length < small_size and
            abs(face.CenterOfMass.z - z) < small_size)
