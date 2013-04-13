# -*- coding: utf-8 -*-
# This script should not depend any module except standard library.
import os
import sys
import glob
import shutil
import subprocess
from os.path import expandvars, expanduser, join, abspath, relpath, exists
from os.path import basename, dirname, normcase, splitext


repository_root = expandvars(r'$DROPBOX_PATH\home\SublimeText')
dry_run = False

config = {
    # TODO cooperate with "folder_exclude_patterns" in .sublime-project
    'additional_exclude_packages': [
        'thirdparty',
        'PyV8',
    ],
    'exclude_options': [
        # ignore directory
        '/xd',
        '.git',
        '.hg',
        'SublimeREPLHistory',  # User/SublimeREPLHistory
        'OmniMarkupPreviewer',  # User/OmniMarkupPreviewer
        'node_modules',
        'packages',
        '__*',
        # ignore file
        '/xf',
        '*.pyc',
        '*.cache',
        '*.json',
        '*.log',
        'imesupport_hook_x64.dll',
        'imesupport_hook_x86.dll',
        '_*.sublime-macro',
        '*.sublime-workspace',
        # '*.sublime-settings',
        'Package Control.last-run',
        'Package Control.sublime-settings',
        'FileHistory.sublime-settings',
        'SublimeServer.sublime-settings',
        'encoding_cache.json',  # ConvertUTF8
        'MediaPlayer 0*',
    ]
}


def on_pre_sync(src, dest):
    print('external_package_sync: src: ' + src + ' dest: ' + dest)


repo_base = None
packages_path = None


# Hide the console window on Windows
startupinfo = None
if os.name == "nt":
    startupinfo = subprocess.STARTUPINFO()
    if hasattr(subprocess, 'STARTF_USESHOWWINDOW'):
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        # Workaround for Python 2.7
        import _subprocess
        startupinfo.dwFlags |= _subprocess.STARTF_USESHOWWINDOW


def init(packages=None):
    global repo_base
    global packages_path
    repo_base = repository_root
    packages_path = packages if packages else sublime_packages_path()


def description():
    print('repo_base: ' + repo_base)
    print('packages_path: ' + packages_path)


def sublime_version():
    try:
        import sublime
        return int(sublime.version()) // 1000
    except ImportError:
        try:
            version = int(sys.argv[1])
            if version < 2 or 3 < version:
                raise Exception('Version Error')
            return version
        except (IndexError, ValueError):
            raise Exception('Version Error')


def sublime_packages_path():
    try:
        import sublime
        return sublime.packages_path()
    except ImportError:
        version = sublime_version()
        if os.name == 'nt':
            return expandvars('$APPDATA\Sublime Text %d\Packages' % version)
        elif os.name == 'mac':
            return expanduser(expandvars('~/Library/Application Support/Sublime Text %d/Packages/' % version))
        elif os.name == 'posix':
            return expanduser(expandvars('~/.config/sublime-text-2/Packages/' % version))
        else:
            raise NotImplementedError()


def input_ok_cancel(message):
    try:
        import sublime
        return sublime.ok_cancel_dialog(message)
    except ImportError:
        if __name__ != '__main__':
            # Do not prompt on running tests.
            return True
        ret = raw_input(message + '\n(input "ok" or "cancel"):')
        return ret == 'ok'


def error_message(message):
    try:
        import sublime
        return sublime.error_message(message)
    except ImportError:
        print(message)


def load_json(fname):
    import json
    with open(fname, 'r') as f:
        text = f.read()
    return json.JSONDecoder(strict=False).decode(text)


def repository_packages():
    packages = glob.glob(join(repo_base, '*'))
    return [basename(i) for i in packages]


def all_packages():
    packages = glob.glob(join(packages_path, '*'))
    return [basename(i) for i in packages]


def installed_packages():
    settings = load_json(join(packages_path, 'User', 'Package Control.sublime-settings'))
    return settings['installed_packages']


def pristine_packages():
    packages = []
    # Pristine Packages for Sublime Text 2
    pristine = join(dirname(packages_path), 'Pristine Packages')
    if exists(pristine):
        full_paths = glob.glob(join(pristine, '*.sublime-package'))
        packages += [splitext(basename(path))[0] for path in full_paths]

    # Pristine Packages for Sublime Text 3
    if os.name == 'nt':
        pristine = expandvars(r'$PROGRAMFILES\Sublime Text 3\Packages')
        if exists(pristine):
            full_paths = glob.glob(join(pristine, '*.sublime-package'))
            packages += [splitext(basename(path))[0] for path in full_paths]

    while 'User' in packages:
        packages.remove('User')
    return packages


def package_sync_status():
    repository = repository_packages()
    packages = all_packages()
    installed = installed_packages()
    pristine = pristine_packages()
    exclude = list(set(pristine) | set(installed) | set(config['additional_exclude_packages']))
    not_package_controled = list(set(packages) - set(pristine) - set(installed))
    # user_installed_packages = list(set(packages) - set(pristine))
    unknown = list(set(not_package_controled) - set(repository))
    return {
        'exclude': exclude,
        'add': list(set(repository) - set(packages) - set(exclude)),
        'remove': list(set(packages) - set(repository) - set(exclude)),
        'sync': list(set(packages) & set(repository)),
        'not_package_controled': not_package_controled,
        # 'user_installed_packages': user_installed_packages,
        'unknown': unknown,
    }


def execute_sync(src, dest, dest_exclude=[]):
    if os.name == 'nt':
        try:
            extra = []
            if dry_run:
                extra.append('/L')
            dest_exclude = [join(dest, i) for i in dest_exclude]
            cmd = ['robocopy', src, dest, '/mir'] + extra + config['exclude_options'] + ['/xd'] + dest_exclude
            subprocess.check_call(cmd, startupinfo=startupinfo)
        except subprocess.CalledProcessError as e:
            if e.returncode > 3:
                error_message(
                    'external_package_sync: returncode: ' + str(e.returncode) + '\n' +
                    'external_package_sync: command line:\n' +
                    ' '.join([s if s.count(' ') == 0 else '"' + s + '"' for s in cmd]))
                raise
    else:
        raise NotImplementedError()


def sync_all_packages():
    status = package_sync_status()
    on_pre_sync(repo_base, packages_path)
    if len(status['add']) > 0 or len(status['remove']) > 0:
        if not input_ok_cancel('\n'.join([
            'external_package_sync: Continue sync?',
            'add: ' + ', '.join(status['add']),
            'remove: ' + ', '.join(status['remove']),
        ])):
            print('external_package_sync: canceled.')
            return
    execute_sync(repo_base, packages_path, status['exclude'])


# def sync_file():
#     for dest, src in sync_file_list.items():
#         subprocess.check_call(['xcopy', '/D'] + src + [dest], startupinfo=startupinfo)


try:
    def path_starts_with(a, start_str):
        return normcase(a).startswith(normcase(start_str))

    def is_under_package(path):
        return path_starts_with(abspath(path), sublime_packages_path())

    def is_under_repository(path):
        return path_starts_with(path, repo_base)

    def get_package_relative_path(path):
        try:
            return relpath(path, repo_base)
        except ValueError:  # ValueError: path is on drive D:, start on drive C:
            return None

    def get_package_name(path):
        rel = get_package_relative_path(path)
        if not rel:
            return None
        if os.sep in rel:
            rel = rel[:rel.index(os.sep)]
        return rel

    def get_other_path(path):
        rel = get_package_relative_path(path)
        if not rel:
            return None
        return join(packages_path, rel)

    # def get_pair_path(fname):
    #     for pair in pair_path_list:
    #         for base in pair:
    #             if path_starts_with(abspath(fname), base):
    #                 return pair
    #     return None

    def reload_module(relfile):
        for mod in sys.modules.values():
            if mod and hasattr(mod, '__file__'):
                path = mod.__file__
                if path.endswith('.pyc'):
                    path = path[:-1]
                if path.endswith(relfile):
                    print('external_package_sync: Reloading submodule: ' + mod.__file__)
                    reload(mod)
                    return

    import sublime
    import sublime_plugin

    def can_sync(repo_file):
        import filecmp
        if not is_under_repository(repo_file):
            return False
        other = get_other_path(repo_file)
        if exists(other) and not filecmp.cmp(repo_file, other):
            if not sublime.ok_cancel_dialog('external_package_sync: file content is not same. overwrite it?' + '\n' + repo_file + '\n' + other):
                return False
        return True

    class ExternalPackageSyncListener(sublime_plugin.EventListener):
        def on_load(self, view):
            if is_under_package(view.file_name()):
                view.set_read_only(True)

        def on_pre_save(self, view):
            if view.file_name() and can_sync(view.file_name()):
                view.settings().set('external_package_sync_can_sync', True)

        def on_post_save(self, view):
            if view.settings().get('external_package_sync_can_sync', False):
                view.settings().erase('external_package_sync_can_sync')
                sync_all_packages()
                # self.extra_ops(view, fname, repo, package)
                # self.reload_submodule(view, fname, repo, package)

        # def extra_ops(self, view, fname, repo, package):
        #     # FIXME Force reload sublime-project.
        #     if view.file_name().endswith('.sublime-project'):
        #         for g in glob.glob(join(package, '**', basename(view.file_name()))):
        #             touch(g)

        # def reload_submodule(self, fname, repo, package):
        #     # FIXME
        #     from os.path import relpath, dirname

        #     try:
        #         rel = relpath(fname, repo)
        #     except ValueError:  # ValueError: path is on drive D:, start on drive C:
        #         return
        #     if dirname(rel) == '':
        #         # top level modules will be reload automatically.
        #         return
        #     reload_module(rel)

    class ExternalPackageSyncCommand(sublime_plugin.ApplicationCommand):
        def run(self):
            sync_all_packages()
            # sync_file()

    class ExternalPackageDiffCommand(sublime_plugin.TextCommand):
        def run(self, edit):
            # pair = get_pair_path(self.view.file_name())
            # if pair:
            #     subprocess.Popen([
            #         expandvars(r"$PROGRAMFILES\WinMerge\WinMergeU.exe"), '/r', pair[0], pair[1]])
            #     return
            package = get_package_name(self.view.file_name())
            if not package:
                return
            subprocess.Popen([
                expandvars(r"$PROGRAMFILES\WinMerge\WinMergeU.exe"), '/r',
                join(repo_base, package), join(packages_path, package)])

    class ExternalPackageEditCopyCommand(sublime_plugin.TextCommand):
        def run(self, edit):
            src = self.view.file_name()
            dest = join(repo_base, 'User', basename(src))
            if src.endswith('.py'):
                root, ext = splitext(dest)
                dest = root + '2' + ext
            shutil.copyfile(src, dest)
            self.view.window().open_file(dest)

        def is_enabled(self):
            return (self.view.file_name() and
                    self.view.file_name().startswith(sublime.packages_path()))

    class InstalledPackageListCommand(sublime_plugin.ApplicationCommand):
        def run(self):
            for i in package_sync_status().items():
                print(i)

    def plugin_loaded():
        init()

    if int(sublime.version()) < 3000:
        plugin_loaded()

except ImportError:
    pass


import unittest
import tempfile
from os.path import isdir
from contextlib import contextmanager


class Test(unittest.TestCase):
    test_src = join(abspath(dirname(__file__)), 'Backup')
    test_dest = join(tempfile.gettempdir(), 'Sublime Packages')

    def setUp(self):
        self.clean_dir(self.test_dest)
        with pushd(self.test_dest):
            self.make_pseudo_dest()

        init(packages=self.test_dest)

    @staticmethod
    def clean_dir(dir_path):
        if exists(dir_path):
            for child in os.listdir(dir_path):
                path = join(dir_path, child)
                if isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        else:
            os.mkdir(dir_path)

    def make_pseudo_dest(self):
        os.mkdir('User')
        os.mkdir('LiveDevelopment')
        os.mkdir('Linter')
        with open('User/Package Control.sublime-settings', 'w') as f:
            f.write("""
                {
                    "installed_packages":
                    [
                        "LiveDevelopment",
                        "Linter"
                    ]
                }
                """)

    def test_sync2(self):
        test_excludes = ['LiveDevelopment']
        execute_sync(self.test_src, self.test_dest, test_excludes)
        for name in test_excludes:
            self.assertTrue(exists(join(self.test_dest, name)))


class TestSync(Test):
    def test_xxx(self):
        sync_all_packages()


@contextmanager
def pushd(to):
    old_cwd = os.getcwd()
    os.chdir(to)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def main():
    init()
    description()
    for i in package_sync_status().items():
        print(i)
    sync_all_packages()

if __name__ == '__main__':
    if '--dry-run' in sys.argv:
        dry_run = True
    # sys.argv.append(2)
    main()
