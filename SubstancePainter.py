import time
from FranticX.Processes import *
from Deadline.Plugins import *
from Deadline.Scripting import *

# from process_wrapper import Painter
import httplib
import json
import base64

STARTUP_WAITING_TIME = 10
PROCESS_NAME = "Substance Painter Process"


def GetDeadlinePlugin():
    return SubstancePainterPlugin()


def CleanupDeadlinePlugin(deadlinePlugin):
    deadlinePlugin.Cleanup()


class SubstancePainterPlugin(DeadlinePlugin):
    def __init__(self):
        self.InitializeProcessCallback += self.InitializeProcess
        self.StartJobCallback += self.StartJob
        self.RenderTasksCallback += self.RenderTasks
        self.EndJobCallback += self.EndJob

    def Cleanup(self):
        del self.InitializeProcessCallback
        del self.StartJobCallback
        del self.RenderTasksCallback
        del self.EndJobCallback

    # noinspection PyAttributeOutsideInit
    def InitializeProcess(self):
        self.SingleFramesOnly = True
        self.PluginType = PluginType.Advanced

    def StartJob(self):
        process = SubstancePainterProces(self)
        self.StartMonitoredManagedProcess(PROCESS_NAME, process)
        self.SetStatusMessage("Waiting to start")
        time.sleep(STARTUP_WAITING_TIME)

    def RenderTasks(self):
        port = int(self.GetConfigEntry("SubstancePainterPort"))
        painter = Painter(port)
        print 'checking connection'
        self.SetStatusMessage("Connecting")
        painter.checkConnection()

        project_file = self.GetPluginInfoEntry("ProjectFile").replace("\\", "/")
        preset = self.GetPluginInfoEntry("Preset").replace("\\", "/")
        export_path = self.GetPluginInfoEntry("ExportPath").replace("\\", "/")
        format_ = self.GetPluginInfoEntry("Format")
        stack_paths = json.dumps(self.GetPluginInfoEntryWithDefault("TextureSets", "").split(","))
        bit_depth = int(self.GetPluginInfoEntryWithDefault("BitDepth", "8"))

        map_info = json.dumps(dict(bitDepth=bit_depth))

        self.SetStatusMessage("Opening file")
        print 'opening file', project_file
        if not project_file.startswith("file:///"):
            project_file = "file:///" + project_file
        print painter.execScript('alg.project.open("{}")'.format(project_file))

        self.SetStatusMessage("Exporting")
        command = 'alg.mapexport.exportDocumentMaps("{preset}", "{export_path}", "{format}", {map_info}, {stack_paths});'.format(
            preset=preset, export_path=export_path, format=format_, map_info=map_info, stack_paths=stack_paths)
        print 'executing command', command
        print painter.execScript(command)

    def EndJob(self):
        self.ShutdownMonitoredManagedProcess(PROCESS_NAME)


class SubstancePainterProces(ManagedProcess):
    def __init__(self, deadline_plugin):
        self.deadline_plugin = deadline_plugin
        self.RenderExecutableCallback += self.RenderExecutable
        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderArgumentCallback += self.RenderArgument

    def Cleanup(self):
        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback

    def InitializeProcess(self):
        pass

    def RenderExecutable(self):
        return self.deadline_plugin.GetConfigEntry("SubstancePainterRenderExecutable")

    def RenderArgument(self):
        arguments = " --disable-version-checking"
        return arguments


###############################################################################################
# Const data
###############################################################################################

# Json server connection
_PAINTER_ROUTE = '/run.json'
_HEADERS = {'Content-type': 'text/plain', 'Accept': 'application/json'}


###############################################################################################
# Exceptions
###############################################################################################

# Generic exception on the Painter class
class PainterError(Exception):
    def __init__(self, message):
        super(PainterError, self).__init__(message)


class ExecuteScriptError(PainterError):
    def __init__(self, data):
        super(PainterError, self).__init__('An error occured when executing script: {0}'.format(data))


###############################################################################################
# Remote Substance Painter control
###############################################################################################

class Painter:
    def __init__(self, port=60041, host='localhost'):
        self._host = host
        self._port = port

    # Execute a HTTP POST request to the Substance Painter server and send/receive JSON data
    def _jsonPostRequest(self, route, body):
        connection = httplib.HTTPConnection(self._host, self._port, timeout=3600)
        connection.request('POST', route, body, _HEADERS)
        response = connection.getresponse()

        data = json.loads(response.read().decode('utf-8'))
        connection.close()

        if type(data) == dict and 'error' in data:
            raise ExecuteScriptError(data['error'])
        return data

    def checkConnection(self):
        connection = httplib.HTTPConnection(self._host, self._port)
        connection.connect()

    # Execute a JavaScript script
    def execScript(self, script):
        main = base64.b64encode(script.encode('utf-8'))
        return self._jsonPostRequest(_PAINTER_ROUTE, ('{"js":"' + main.decode('utf-8') + '"}').encode('utf-8'))
