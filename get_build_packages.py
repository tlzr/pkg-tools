#!/usr/bin/env python
"""Working with packages"""

import apt
import argparse
import os
import re
import sys
import yaml
from cStringIO import StringIO
from subprocess import Popen, PIPE

package_regexp = re.compile('(\s+)?(?P<package_name>[a-z0-9-]+)(\s+)?'
                            '(?P<package_version>\([<>=a-z0-9-.: ]+\))?'
                            ',?(\s+)?')
package_name_re = re.compile('^[a-z0-9-.]+')
package_version_re = re.compile('\([<>=a-z0-9-.:~ ]+\)$')
package_section_re = re.compile('^[A-z0-9-.]+:')
control_package = re.compile('(?P<package>Package:)\s*'
                             '(?P<package_name>[a-z0-9-]+)')
valid_req_line_re = re.compile('^[A-z0-9-.<>=,!]+')
req_name_re = re.compile('^[A-z0-9-.]+')
req_version_re = re.compile('([0-9-.<>=,!]+)?$')
pkg_uri_re = re.compile('^(https?://[A-z0-9-.:]+/)')

class TrustyPackages:

    """Package processing
    """
    def __init__(self):
        """Docstring"""
        self.package_dic = {}
        self.requirements_doc = {}
        self.accordance_dictionary = {}
        self.control_mem = ''
        self.packages_in_control = []
        self.control_parsed = ''

    def get_packages(self, line):
        """Docstring"""
        packages = package_regexp.match(line)
        if packages:
            return packages
        else:
            return None

    def to_str(self,arr):
        """Docstring"""
        return ''.join(map(str, arr))

    def prepare_control(self, control_file):
        """Docstring"""
        add_identation = False
        with open(control_file, 'r') as control:
            self.control_mem = StringIO()
            for line in control:
                if re.match('^\s*#', line):
                    continue
                match = control_package.match(line)
                if match:
                    if match.group('package_name') \
                    not in self.packages_in_control:
                        self.packages_in_control.append(\
                        match.group('package_name'))
                    line = re.sub('^.*', match.group('package_name')\
                     + ':', line)
                    self.control_mem.write('%s' % line)
                    if not add_identation:
                        add_identation = True
                    continue

                if add_identation:
                    if package_section_re.match(line):
                        words = line.split(' ')
                        if len(words) > 1:
                            for key, value in enumerate(words[1:]):
                                re.sub(':', '', words[key])
                            line = ' '.join(words)
                    else:
                        line = re.sub(':', '', line)

                    line = '  ' + line

                self.control_mem.write('%s' % line)
            self.control = self.control_mem.getvalue()
            self.control_mem.close()
            try:
                self.control_parsed = yaml.safe_load(self.control)
            except ScannerError:
                print "Wrong .yaml file format, please check the content"
                sys.exit(2)

    def fill_package_dictionary(self, control, package_name='source_package'):
        """Docstring"""
        if len(control) > 0:
            parsed_packages = re.sub('\s+', '', control)
            if not package_name in self.package_dic:
                    self.package_dic[package_name] = {}

            for package in parsed_packages.split(','):
                if not package_name_re.match(package):
                    continue

                name = self.to_str(package_name_re.findall(package))
                version = self.to_str(package_version_re.findall(package))
                self.package_dic[package_name][name] = version

    def build_dependencies(self, debug=False):
        """Docstring."""
        build_sections = ['Build-Depends', 'Build-Depends-Indep']
        for section_name in build_sections:
            if self.control_parsed and section_name in self.control_parsed:
                self.fill_package_dictionary(self.control_parsed[section_name])
            else:
                if debug:
                    print('{section_name} - section is absent'.format(section_name=section_name))

    def packages_build_dependencies(self, debug=False):
        """Docstring."""
        build_sections = ['Pre-Depends', 'Depends']
        for package_name in self.packages_in_control:
            for section_name in build_sections:
                if self.control_parsed and section_name in self.control_parsed:
                    self.fill_package_dictionary(self.control_parsed[package_name]\
                    [section_name], package_name)
                else:
                    if debug:
                        print('{section_name} - section is absent'.format(section_name=section_name))

    def load_accordance_dictionary(self, dict_file):
        """Docstring."""
        with open(dict_file, 'r') as dict_yaml:
            try:
                self.accordance_dictionary = yaml.safe_load(dict_yaml)
            except ScannerError as Error:
                print Error
                print "Wrong .yaml file format, please check the content"
                return None

    def parse_requirements(self, requirements_file):
        """Docstring."""
        with open(requirements_file, 'r') as requirements_lines:
            for line in requirements_lines:
                line = re.sub('\s+', '', line)
                match = valid_req_line_re.search(line)
                if match:
                    valid_line = match.group()
                    name = req_name_re.search(valid_line).group()
                    version = req_version_re.search(valid_line).group()
                    self.requirements_doc[name] = version.split(',')

    def prepare_apt(self, version, update_cache=False, cache_path='cache'):
        try:
            current_dir = os.getcwd()
        except:
            current_dir = './'

        path_to_cache = os.path.join(current_dir, cache_path, version)
        path_to_sources_list = os.path.join(path_to_cache, 'etc/apt/sources.list')
        apt.cache.Cache(rootdir=path_to_cache)

        fuel_version = float(version)
        if fuel_version < 7:
            if fuel_version >= 6.1:
                release = 'trusty'
                custom_repo = """
deb http://osci-obs.vm.mirantis.net:82/{release}-fuel-{version}-stable/ubuntu/ ./'
""".format(version=fuel_version, release=release)
            else:
                release = 'precise'
                custom_repo = """
deb http://osci-obs.vm.mirantis.net:82/ubuntu-fuel-{version}-stable/ubuntu/ ./
""".format(version=fuel_version)

            sources = """
#------------------------------------------------------------------------------#
#                            MIRANTIS UBUNTU REPOS                             #
#------------------------------------------------------------------------------#
###### Ubuntu Main Repos
deb http://mirrors.srt.mirantis.net/ubuntu/ {release} main restricted
deb-src http://mirrors.srt.mirantis.net/ubuntu/ {release} main restricted
deb http://mirrors.srt.mirantis.net/ubuntu/ {release}-updates main restricted
deb-src http://mirrors.srt.mirantis.net/ubuntu/ {release}-updates main restricted
deb http://mirrors.srt.mirantis.net/ubuntu/ {release} universe
deb-src http://mirrors.srt.mirantis.net/ubuntu/ {release} universe
deb http://mirrors.srt.mirantis.net/ubuntu/ {release}-updates universe
deb-src http://mirrors.srt.mirantis.net/ubuntu/ {release}-updates universe
deb http://mirrors.srt.mirantis.net/ubuntu/ {release}-security main restricted
deb-src http://mirrors.srt.mirantis.net/ubuntu/ {release}-security main restricted
deb http://mirrors.srt.mirantis.net/ubuntu/ {release}-security universe
deb-src http://mirrors.srt.mirantis.net/ubuntu/ {release}-security universe
##### Custom-Built Packages
            """.format(version=fuel_version, release=release)
            sources += custom_repo
        else:
            release = 'trusty'
            sources = """
#------------------------------------------------------------------------------#
#                            OFFICIAL UBUNTU REPOS                             #
#------------------------------------------------------------------------------#
###### Ubuntu Main Repos
deb http://ua.archive.ubuntu.com/ubuntu/ {release} main universe
###### Ubuntu Update Repos
deb http://ua.archive.ubuntu.com/ubuntu/ {release}-security main universe
deb http://ua.archive.ubuntu.com/ubuntu/ {release}-updates main universe
deb http://ua.archive.ubuntu.com/ubuntu/ {release}-proposed main universe
##### Custom-Built Packages
deb http://obs-1.mirantis.com:82/trusty-fuel-{version}-stable/ubuntu/ ./
""".format(version=fuel_version, release=release)

        with open(path_to_sources_list, 'w') as file:
            file.write(sources)
            file.close()

        cache = apt.cache.Cache(rootdir=path_to_cache)

        if update_cache:
            cache.update()

        return cache

def main(args):
    packages = TrustyPackages()
    if args.fuel_version:
        repo_cache = packages.prepare_apt(args.fuel_version, args.update_cache)
    packages.prepare_control(args.control_file_location)

    if args.requirements:
        packages.load_accordance_dictionary('accordance_dictionary.yaml')
        packages.parse_requirements(args.requirements)
        packages.build_dependencies(args.debug)
        packages.packages_build_dependencies(args.debug)
        packages.packages_in_control.append('source_package')

        for required_package in packages.requirements_doc:

            if required_package in packages.accordance_dictionary:
                pkg_name = packages.accordance_dictionary[required_package]
                if repo_cache and (pkg_name in repo_cache):
                    pkg_in_repo = repo_cache[pkg_name]
                    if repo_cache.is_virtual_package(pkg_name):
                        print('ATTENTION: Package is Virtual!')
                    for package in pkg_in_repo.versions:
                        pkg_uri_match = pkg_uri_re.match(package.uri)
                        if pkg_uri_match:
                            pkg_uri = pkg_uri_match.group()
                        else:
                            pkg_uri = package.uri
                        print('r: {package_version} ({package_uri})'.format(package_uri=pkg_uri, package_version=package.version))
            else:
                if args.debug:
                    for package in repo_cache:
                        if required_package.lower() in package.name:
                            print('Possible package name:\n{required_package}: {package_name}'.format(package_name=package.name, required_package=required_package))
                    print 'Not in a dictionary: ' + required_package
                pkg_name = required_package

            for package_name in packages.packages_in_control:
                if package_name in packages.package_dic and \
                   pkg_name in packages.package_dic[package_name]:
                    print package_name + ":", required_package, \
                    packages.requirements_doc[required_package], '<===>', \
                    pkg_name, packages.package_dic[package_name][pkg_name]
    else:
        for package in packages.package_dic.keys():
            proc = Popen(['apt-cache', 'madison', package], stdout=PIPE,\
                         stderr=PIPE)
            stdout_value = proc.communicate()[0]
            print stdout_value

    if repo_cache:
        repo_cache.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get deploy tasks by role.')
    parser.add_argument("control_file_location", type=str, help="Path to the\
                         control file", default='debian/control')
    parser.add_argument('-r', '--requirements', metavar=('REQS'), type=str,
                        help='requirements file location', default='reqs')
    parser.add_argument('-f', '--fuel-version', metavar=('FVER'), type=str,
                        help='Fuel version', default='7.0')
    parser.add_argument('-u', '--update-cache', action='store_true',
                        help='Force cache update')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Verbosity level')
    parser.add_argument('-i', '--info', action='version',
                        version='Version: 1.0')
    args = parser.parse_args()

    main(args)
