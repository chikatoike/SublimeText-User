import os, sys
import threading
import subprocess
import functools
import time


helper_script = os.path.abspath(__file__)


class ProcessListener(object):
    def on_data(self, proc, data):
        pass

    def on_data_error(self, proc, data):
        self.on_data(proc, data)

    def on_finished(self, proc):
        pass

# Encapsulates subprocess.Popen, forwarding stdout to a supplied
# ProcessListener (on a separate thread)
class AsyncProcess(object):
    def __init__(self, cmd, shell_cmd, env, listener,
            helper=False,
            # "path" is an option in build systems
            path="",
            # "shell" is an options in build systems
            shell=False):

        if os.name != "nt":
            helper = False
        stdin = None
        if helper:
            stdin = subprocess.PIPE
            if cmd:
                python_exe = which('python.exe')
                cmd = [python_exe, helper_script] + cmd

        if not shell_cmd and not cmd:
            raise ValueError("shell_cmd or cmd is required")

        if shell_cmd and not isinstance(shell_cmd, str):
            raise ValueError("shell_cmd must be a string")

        self.listener = listener
        self.killed = False

        self.start_time = time.time()

        # Hide the console window on Windows
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # Set temporary PATH to locate executable in cmd
        if path:
            old_path = os.environ["PATH"]
            # The user decides in the build system whether he wants to append $PATH
            # or tuck it at the front: "$PATH;C:\\new\\path", "C:\\new\\path;$PATH"
            os.environ["PATH"] = os.path.expandvars(path)

        proc_env = os.environ.copy()
        proc_env.update(env)
        for k, v in proc_env.items():
            proc_env[k] = os.path.expandvars(v)

        if sys.version_info < (3, 0, 0):
            for k, v in proc_env.items():
                proc_env[k] = v.encode(sys.getfilesystemencoding())

        try:
            if shell_cmd and sys.platform == "win32":
                # Use shell=True on Windows, so shell_cmd is passed through with the correct escaping
                self.proc = subprocess.Popen(shell_cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=True, stdin=stdin)
            elif shell_cmd and sys.platform == "darwin":
                # Use a login shell on OSX, otherwise the users expected env vars won't be setup
                self.proc = subprocess.Popen(["/bin/bash", "-l", "-c", shell_cmd], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=False, stdin=stdin)
            elif shell_cmd and sys.platform == "linux":
                # Explicitly use /bin/bash on Linux, to keep Linux and OSX as
                # similar as possible. A login shell is explicitly not used for
                # linux, as it's not required
                self.proc = subprocess.Popen(["/bin/bash", "-c", shell_cmd], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=False, stdin=stdin)
            else:
                # Old style build system, just do what it asks
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=shell, stdin=stdin)
        finally:
            if path:
                os.environ["PATH"] = old_path

        if self.proc.stdout:
            threading.Thread(target=self.read_stdout).start()

        if self.proc.stderr:
            threading.Thread(target=self.read_stderr).start()

    def kill(self):
        if not self.killed:
            self.killed = True
            if sublime.platform() == 'windows':
                self.proc.stdin.close()
                self.proc.wait()
                # self.proc.terminate()
            else:
                self.proc.terminate()
            self.listener = None

    def poll(self):
        return self.proc.poll() == None

    def exit_code(self):
        return self.proc.poll()

    def read_stdout(self):
        while True:
            data = os.read(self.proc.stdout.fileno(), 2**15)

            if len(data) > 0:
                if self.listener:
                    self.listener.on_data(self, data)
            else:
                self.proc.stdout.close()
                if self.listener:
                    self.listener.on_finished(self)
                break

    def read_stderr(self):
        while True:
            data = os.read(self.proc.stderr.fileno(), 2**15)

            if len(data) > 0:
                if self.listener:
                    self.listener.on_data_error(self, data)
            else:
                self.proc.stderr.close()
                break


def which(command):
    for path in os.environ["PATH"].split(os.pathsep):
        if os.path.exists(path) and command in os.listdir(path):
            return os.path.join(path, command)


if __name__ == '__main__':
    import ctypes

    CTRL_C_EVENT = 0
    CTRL_BREAK_EVENT = 1

    def SendCtrlC(proc, with_myself):
        ctypes.windll.kernel32.FreeConsole()
        ctypes.windll.kernel32.AttachConsole(proc.pid)
        if not with_myself:
            ctypes.windll.kernel32.SetConsoleCtrlHandler(0, 1)
        ctypes.windll.kernel32.GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)

    class CommandRunner(ProcessListener):
        def on_data(self, proc, data):
            sys.stdout.write(data)

        def on_data_error(self, proc, data):
            sys.stderr.write(data)

        def on_finished(self, proc):
            exit_code = proc.exit_code()
            if exit_code == 0 or exit_code is None:
                os._exit(0)
            else:
                os._exit(exit_code)

    def run(cmd, shell_cmd, **kwargs):
        # not supported shell_cmd
        # assert shell_cmd is not None
        async = AsyncProcess(cmd, shell_cmd, {}, CommandRunner(), **kwargs)
        # Waiting for kill from parent process.
        data = sys.stdin.read(1)
        if len(data) > 0:
            assert False, "Unexpected input"
        # # SendCtrlC(async.proc, True)

    if len(sys.argv) > 1:
        run(sys.argv[1:], None, shell=False)
    else:
        run(None, 'python.exe -c "import time; while True: print(time); time.sleep(1)"')
        # run(None, 'python.exe -c "print(123)"')
        # run(None, 'python.exe --help1')
    sys.exit()


import sublime
import sublime_plugin


class ExecCommand(sublime_plugin.WindowCommand, ProcessListener):
    def run(self, cmd = None, shell_cmd = None, file_regex = "", line_regex = "", working_dir = "",
            encoding = "utf-8", env = {}, quiet = False, kill = False,
            word_wrap = True, syntax = None,
            # Catches "path" and "shell"
            **kwargs):

        if kill:
            if self.proc:
                self.proc.kill()
                self.proc = None
                self.append_string(None, "[Cancelled]")
            return

        if not hasattr(self, 'output_view'):
            # Try not to call get_output_panel until the regexes are assigned
            if hasattr(self.window, 'create_output_panel'):
                self.output_view = self.window.create_output_panel("exec")
            else:
                self.output_view = self.window.get_output_panel("exec")

        # Default the to the current files directory if no working directory was given
        if (working_dir == "" and self.window.active_view()
                        and self.window.active_view().file_name()):
            working_dir = os.path.dirname(self.window.active_view().file_name())

        self.output_view.settings().set("result_file_regex", file_regex)
        self.output_view.settings().set("result_line_regex", line_regex)
        self.output_view.settings().set("result_base_dir", working_dir)
        self.output_view.settings().set("word_wrap", word_wrap)
        self.output_view.settings().set("line_numbers", False)
        self.output_view.settings().set("gutter", False)
        self.output_view.settings().set("scroll_past_end", False)
        if syntax:
            if hasattr(self.window, 'assign_syntax'):
                self.output_view.assign_syntax(syntax)
            else:
                self.output_view.set_syntax_file(syntax)

        # Call create_output_panel a second time after assigning the above
        # settings, so that it'll be picked up as a result buffer
        if hasattr(self.window, 'create_output_panel'):
            self.window.create_output_panel("exec")
        else:
            self.window.get_output_panel("exec")

        self.encoding = encoding
        self.quiet = quiet

        self.proc = None
        if not self.quiet:
            if shell_cmd:
                print("Running " + shell_cmd)
            else:
                print("Running " + " ".join(cmd))
            sublime.status_message("Building")

        show_panel_on_build = sublime.load_settings("Preferences.sublime-settings").get("show_panel_on_build", True)
        if show_panel_on_build:
            self.window.run_command("show_panel", {"panel": "output.exec"})

        merged_env = env.copy()
        if self.window.active_view():
            user_env = self.window.active_view().settings().get('build_env')
            if user_env:
                merged_env.update(user_env)

        # Change to the working dir, rather than spawning the process with it,
        # so that emitted working dir relative path names make sense
        if working_dir != "":
            os.chdir(working_dir)

        self.debug_text = ""
        if shell_cmd:
            self.debug_text += "[shell_cmd: " + shell_cmd + "]\n"
        else:
            self.debug_text += "[cmd: " + str(cmd) + "]\n"
        self.debug_text += "[dir: " + str(os.getcwd()) + "]\n"
        if "PATH" in merged_env:
            self.debug_text += "[path: " + str(merged_env["PATH"]) + "]"
        else:
            self.debug_text += "[path: " + str(os.environ["PATH"]) + "]"

        try:
            # Forward kwargs to AsyncProcess
            self.proc = AsyncProcess(cmd, shell_cmd, merged_env, self, **kwargs)
        except Exception as e:
            self.append_string(None, str(e) + "\n")
            self.append_string(None, self.debug_text + "\n")
            if not self.quiet:
                self.append_string(None, "[Finished]")

    def is_enabled(self, kill = False):
        if kill:
            return hasattr(self, 'proc') and self.proc and self.proc.poll()
        else:
            return True

    def append_data(self, proc, data):
        if proc != self.proc:
            # a second call to exec has been made before the first one
            # finished, ignore it instead of intermingling the output.
            if proc:
                proc.kill()
            return

        try:
            str = data.decode(self.encoding)
        except:
            str = "[Decode error - output not " + self.encoding + "]\n"
            proc = None

        # Normalize newlines, Sublime Text always uses a single \n separator
        # in memory.
        str = str.replace('\r\n', '\n').replace('\r', '\n')

        self.output_view.run_command('append', {'characters': str, 'force': True, 'scroll_to_end': True})

    def append_string(self, proc, str):
        self.append_data(proc, str.encode(self.encoding))

    def finish(self, proc):
        if not self.quiet:
            elapsed = time.time() - proc.start_time
            exit_code = proc.exit_code()
            if exit_code == 0 or exit_code == None:
                self.append_string(proc,
                    ("[Finished in %.1fs]" % (elapsed)))
            else:
                self.append_string(proc, ("[Finished in %.1fs with exit code %d]\n"
                    % (elapsed, exit_code)))
                # self.append_string(proc, self.debug_text)

        if proc != self.proc:
            return

        errs = self.output_view.find_all_results()
        if len(errs) == 0:
            sublime.status_message("Build finished")
        else:
            sublime.status_message(("Build finished with %d errors") % len(errs))

    def on_data(self, proc, data):
        sublime.set_timeout(functools.partial(self.append_data, proc, data), 0)

    def on_finished(self, proc):
        sublime.set_timeout(functools.partial(self.finish, proc), 0)


if int(sublime.version()) < 3000:
    class AppendCommand(sublime_plugin.TextCommand):
        def run(self, edit, characters, force=False, scroll_to_end=False):
            view = self.view
            selection_was_at_end = (len(view.sel()) == 1
                and view.sel()[0]
                    == sublime.Region(view.size()))
            view.set_read_only(False)
            edit = view.begin_edit()
            view.insert(edit, view.size(), characters)
            if selection_was_at_end:
                view.show(view.size())
            view.end_edit(edit)
            view.set_read_only(True)
