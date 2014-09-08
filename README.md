S4Py
====

S4Py is a tool and library for working with Sims 4 content. Right now
it's fairly limited, but it will eventually do everything from
low-level inspection of Sims4 data files to compiling a high-level
description of what you want your mod to do from a single
user-friendly input file into a package complete with
automatically-generated string tables and SimData files (and checking
to make sure that the tunables that you use are valid).

Because I've been developing software for a while now, I have fairly
strong opinions about how builds should work. For example, the build
tools should NEVER modify a file that you as a user directly edit; in
fact, the output of a build step should never depend whether the
output file existed before the build step executed, much less depend
on its prior contents. This means that for the low-level build tool,
if you maintain your assets as loose files in a directory and then run

    s4py package assemble -o mymod.package sourcedir

`mymod.package` will contain ONLY the resources that were in
sourcedir.

Status
======

Right now s4py is not going to be useful to you unless you want to do
significant development work; it's in the very early stages of
development. You can expect that there will be an XML-to-SimData
compiler fairly soon; the assemble tool will follow fairly shortly
after that.  If there are any specific tools that you need, don't
hesitate to let me know by filing a feature request.

All that s4py can do right now is list and extract the contents of a
package.

Installation
============

First, make sure that you have Python 3.3 or above installed. Then, run

    python setup.py install

If you want to work on s4py, I recommend instead running

    python setup.py develop

Either way, you will then have the s4py binary available for use. Run
it for further instructions.

