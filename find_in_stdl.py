#!/usr/bin/env python

import argparse
import logging
import os
import sys
import re

from os.path import join
from stdlib_list import stdlib_list

py2_version = "2.7"
py3_version = "3.4"

py2_libraries = stdlib_list(py2_version)
py3_libraries = stdlib_list(py3_version)

import_line_re = re.compile('^(\s+)?import\s|^(\s+)?from\s')
import_from_re = re.compile('^from\s+(?P<module_name>[A-z0-9_.]+)\s+import\s+(?P<imported_modules_names>[A-z0-9_., ]+)')
import_re = re.compile('^import\s+(?P<modules_names>[A-z0-9_., ]+)')
main_module_re = re.compile('^(?P<main_module>[A-z0-9_]+)\.')

modules = []


def module_in_the_line(line, module_list):
    for module in module_list:
        if line.startswith('import ' + module) or line.startswith('from ' + module):
            return True

    return False


def main(args):
    for root, dirs, files in os.walk(args.directory):
        files_in_cur_dir = [join(root,name) for name in files if name.endswith('.py')]
        for file in files_in_cur_dir:
            with open(file) as open_file:
                for line in open_file:
                    if import_line_re.match(line):
                        line = re.sub('^\s+','',line)
                        line = re.sub('\s{2,}',' ',line)

                        if args.exclude and module_in_the_line(line, args.exclude):
                            continue

                        if line.startswith('from'):
                            match = import_from_re.match(line)
                            if match:
                                for module in match.group('imported_modules_names').split(','):
                                    if module:
                                        if match.group('module_name').startswith('.'):
                                            continue

                                        formated_module = match.group('module_name') + '.' + re.sub('(^\s|\s$|\sas\s[A-z0-9._]+)','',module)

                                        if formated_module not in modules:
                                            modules.append(formated_module)
                        else:
                            match = import_re.match(line)

                            if match:
                                for module in match.group('modules_names').split(','):
                                    if module:
                                        if module.startswith('.'):
                                            continue

                                        formated_module = re.sub('(^\s|\s$|\sas\s[A-z0-9._]+)','',module)

                                        if formated_module not in modules:
                                            modules.append(formated_module)

    
    for module in modules:
        main_module = ''
        match = main_module_re.match(module)

        if match:
            main_module = match.group('main_module')

        if module not in py2_libraries:
            if main_module and main_module in py2_libraries:
                print('Main "%s" is in STD-LIB-%s but %s is not. Please check documentation.' % (main_module, py2_version, module))
            else:
                print('Module "%s" is not in STD-LIB-%s' % (module, py2_version))

        if args.py3:
            if module not in py3_libraries:
                if main_module and main_module in py3_libraries:
                    print('Main "%s" is in STD-LIB-%s but %s is not. Please check documentation.' % (main_module, py3_version, module))
                else:
                    print('Module "%s" is not in STD-LIB-%s' % (module, py3_version))



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Show non-standart dependencies.')
    parser.add_argument('-d', '--directory', metavar=('DIR'), type=str,
                        help='Directory', default='.')
    parser.add_argument('-p', '--py3', help='Whether to add py3 support', action='store_true')
    parser.add_argument('-e', '--exclude', nargs='+', metavar=('EXCLUDE_LIST'), type=str,
                    help='Exclude list')

    args = parser.parse_args()

    main(args)
