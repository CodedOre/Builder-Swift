# builder-swift.py
#   Copyright (C) 2019 CodedOre
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import threading
import os

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Ide

class SwiftBuildSystemDiscovery(Ide.SimpleBuildSystemDiscovery):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.props.glob = 'Package.swift'
        self.props.hint = 'builder-swift'
        self.props.priority = 0

class SwiftBuildSystem(Ide.Object, Ide.BuildSystem):
    project_file = GObject.Property(type=Gio.File)
    
    def do_get_id(self):
        return 'swift'
    
    def do_get_display_name(self):
        return 'Swift'
    
    def do_get_priority(self):
        return 0

class SwiftPipelineAddin(Ide.Object, Ide.PipelineAddin):
    """
    The SwiftPipelineAddin is responsible for creating the necessary build
    stages and attaching them to phases of the build pipeline.
    """

    def do_load(self, pipeline):
        context = self.get_context()
        build_system = Ide.BuildSystem.from_context(context)

        if type(build_system) != SwiftBuildSystem:
            return
        
        config = pipeline.get_config()
        builddir = pipeline.get_builddir()
        runtime = config.get_runtime()
        srcdir = pipeline.get_srcdir()

        if not runtime.contains_program_in_path('swift'):
            raise OSError('The runtime must contain swift to build Swift projects')
        
        dependend_launcher = pipeline.create_launcher()
        dependend_launcher.set_cwd(srcdir)
        dependend_launcher.push_argv('swift')
        dependend_launcher.push_argv('package')
        dependend_launcher.push_argv('--build-path')
        dependend_launcher.push_argv(builddir)
        dependend_launcher.push_argv('resolve')
        
        build_launcher = pipeline.create_launcher()
        build_launcher.set_cwd(srcdir)
        build_launcher.push_argv('swift')
        build_launcher.push_argv('build')
        build_launcher.push_argv('--build-path')
        build_launcher.push_argv(builddir)
        
        clean_launcher = pipeline.create_launcher()
        clean_launcher.set_cwd(srcdir)
        clean_launcher.push_argv('swift')
        clean_launcher.push_argv('package')
        clean_launcher.push_argv('--build-path')
        clean_launcher.push_argv(builddir)
        clean_launcher.push_argv('clean')
        
        install_launcher = pipeline.create_launcher()
        install_launcher.set_cwd(srcdir)
        install_launcher.push_argv()
        
        dependend_stage = Ide.PipelineStageLauncher.new(context, dependend_launcher)
        dependend_stage.set_name(_("Resolving Dependencies"))
        self.track(pipeline.attach(Ide.PipelinePhase.DEPENDENCIES, 0, dependend_stage))
        
        build_stage = Ide.PipelineStageLauncher.new(context, build_launcher)
        build_stage.set_name(_("Building project"))
        build_stage.set_clean_launcher(clean_launcher)
        build_stage.connect('query', self._query)
        self.track(pipeline.attach(Ide.PipelinePhase.BUILD, 0, build_stage))
        
        install_stage = Ide.PipelineStageLauncher.new(context, install_launcher)
        install_stage.set_name(_("Installing project"))
        self.track(pipeline.attach(Ide.PipelinePhase.INSTALL, 0, install_stage))
    
    def _query(self, stage, pipeline, targets, cancellable):
        stage.set_completed(False)

class SwiftBuildTarget(Ide.Object, Ide.BuildTarget):
    
    def do_get_install_directory(self):
        return None
    
    def do_get_name(self):
        return 'swift-run'
    
    def do_get_language(self):
        return 'swift'
    
    def do_get_cwd(self):
        context = self.get_context()
        project_file = Ide.BuildSystem.from_context(context).project_file
        if project_file.query_file_type(0, None) == Gio.FileType.DIRECTORY:
            return project_file.get_path()
        else:
            return project_file.get_parent().get_path()
    
    def do_get_priority(self):
        return 0

class SwiftBuildTargetProvider(Ide.Object, Ide.BuildTargetProvider):
    
    def do_get_targets_async(self, cancellable, callback, data):
        task = Ide.Task.new(self, cancellable, callback)
        task.set_priority(GLib.PRIORITY_LOW)
        
        context = self.get_context()
        build_system = Ide.BuildSystem.from_context(context)
        
        if type(build_system) != SwiftBuildSystem:
            task.return_error(GLib.Error('Not swift build system',
                                         domain=GLib.quark_to_string(Gio.io_error_quark()),
                                         code=Gio.IOErrorEnum.NOT_SUPPORTED))
            return
        
        task.targets = [build_system.ensure_child_typed(SwiftBuildTarget)]
        task.return_boolean(True)
    
    def do_get_targets_finish(self, result):
        if result.propagate_boolean():
            return result.targets
