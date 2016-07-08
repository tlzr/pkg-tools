#!/usr/bin/env python

import apt
import argparse
import os
import re
import requests
import sys
import yaml
from cStringIO import StringIO
from subprocess import Popen, PIPE

package_regexp = re.compile('(\s+)?(?P<package_name>[a-z0-9-]+)(\s+)?'
                            '(?P<package_version>\([<>=]+[a-z0-9-.: ]+\))?'
                            ',?(\s+)?')
package_name_re = re.compile('^[a-z0-9-.]+')
package_version_re = re.compile('\([<>=a-z0-9-.:~ ]+\)$')
package_section_re = re.compile('^[A-z0-9-.]+:')
section_re = re.compile('(?P<name>^[A-z0-9-.]+):')
control_package = re.compile('(?P<package>Package:)\s*'
                             '(?P<package_name>[a-z0-9-]+)')
valid_req_line_re = re.compile('^[A-z0-9-.<>=,!]+')
web_link_re = re.compile('^(https?)')
req_name_re = re.compile('^[A-z0-9-.]+')
req_version_re = re.compile('([<>=!]+[a-z0-9-.]+)')
pkg_uri_re = re.compile('^(https?://[A-z0-9-.:]+/)')
pkg_recommended_re = re.compile('(?:\s+)?(?P<package_name>[a-z0-9-.]+)'
                                '(?P<version_space>\s+)?(?:(?P<version_opening_bracket>'
                                '\()(?P<version_relation>(>>|<<|>=|<=|==))'
                                '(?P<relation_space>\s+)?(?P<package_version>[a-z0-9-.:]+)'
                                '(?P<version_closing_bracket>\)))?(?P<comma_space>\s+)?(?P<version_comma>,)?')
package_version_group = re.compile('^(?:\()?(?P<version_relation>>>|<<|>=|<=|==)'
                                   '(?P<package_version>[a-z0-9-.:]+)')
package_version_epoch_re = re.compile('^[0-9]+:')
in_section = re.compile('^\s')


class TrustyPackages:

    """Package processing
    """
    def __init__(self):
        """Docstring"""
        self.package_dic = {}
        self.requirements_doc = {}
        self.accordance_dictionary = {}
        self.control_mem = ''
        self.packages_in_control = ['original_package']
        self.control_parsed = ''
        self.pkg_dictionary = []
        self.verified_pkg_dictionary = []
        self.not_satisfied_pkg_dictionary = []

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

        with open(control_file, 'r') as control:
           section_marker = False
           section_string = ''
           section_name = ''
           package_name = ''
           self.source_package = {}
           self.source_sub_packages = {}

           for line in control:
               if section_marker and in_section.match(line):
                   if section_name not in ['Uploaders','Maintainer','Description']:
                       line = re.sub('(\s|\n)', '', line)
                   else:
                       line = re.sub('(^\s*)', ' ', line)
                   section_string += line
                   continue

               if section_name:
                   if package_name:                       
                       self.source_sub_packages[package_name][section_name] = section_string
                   else:
                       self.source_package[section_name] = section_string

               match = section_re.match(line)
               if match:
                   section_name = match.group('name')
                   if section_name == 'Package':
                       match = control_package.match(line)
                       if match.group('package_name'):
                           package_name = match.group('package_name')
                           self.source_sub_packages[package_name] = {}
                       else:
                           print('Wrong package name!')
                           sys.exit(1)
                   elif section_name == 'Description':
                       line = re.sub('(^'+ section_name +':\s*\n*|\n$)', '', line)
                   else:
                       line = re.sub('('+ section_name +':\s*|^\s|\n)', '', line)
                   section_marker = True
                   section_string = line
                   continue


               section_name = ''
               section_string = ''
               section_marker = False


    def fill_package_dictionary(self, control, package_name='original_package'):
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
                    version = req_version_re.findall(valid_line)
                    self.requirements_doc[name] = version

    def prepare_cache(self, path_to_cache, version):
        cache = apt.cache.Cache(rootdir=path_to_cache)
        path_to_sources_list = os.path.join(path_to_cache, 'etc/apt/sources.list')
        if os.path.exists(path_to_sources_list) and os.stat(path_to_sources_list).st_size == 0:
            if version == 'debian':
                sources = """
deb http://security.debian.org/ jessie main contrib
deb-src http://security.debian.org/ jessie main contrib
deb http://ftp.ua.debian.org/debian/ jessie-updates main contrib
deb-src http://ftp.ua.debian.org/debian/ jessie-updates main contrib
deb http://ftp.ua.debian.org/debian/ sid main contrib
deb-src http://ftp.ua.debian.org/debian/ sid main contrib
deb http://ftp.ua.debian.org/debian/ experimental main contrib
deb-src http://ftp.ua.debian.org/debian/ experimental main contrib
deb http://mitaka-jessie.pkgs.mirantis.com/debian jessie-mitaka-backports main
deb-src http://mitaka-jessie.pkgs.mirantis.com/debian jessie-mitaka-backports main
deb http://mitaka-jessie.pkgs.mirantis.com/debian jessie-mitaka-backports-nochange main
deb-src http://mitaka-jessie.pkgs.mirantis.com/debian jessie-mitaka-backports-nochange main
"""
            elif version == 'mos':
                sources = """
deb http://ru.archive.ubuntu.com/ubuntu/ trusty main restricted
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty main restricted
deb http://ru.archive.ubuntu.com/ubuntu/ trusty-updates main restricted
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty-updates main restricted
deb http://ru.archive.ubuntu.com/ubuntu/ trusty universe
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty universe
deb http://ru.archive.ubuntu.com/ubuntu/ trusty-updates universe
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty-updates universe
deb http://ru.archive.ubuntu.com/ubuntu/ trusty multiverse
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty multiverse
deb http://ru.archive.ubuntu.com/ubuntu/ trusty-updates multiverse
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty-updates multiverse
deb http://ru.archive.ubuntu.com/ubuntu/ trusty-backports main restricted universe multiverse
deb-src http://ru.archive.ubuntu.com/ubuntu/ trusty-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu trusty-security main restricted
deb-src http://security.ubuntu.com/ubuntu trusty-security main restricted
deb http://security.ubuntu.com/ubuntu trusty-security universe
deb-src http://security.ubuntu.com/ubuntu trusty-security universe
deb http://security.ubuntu.com/ubuntu trusty-security multiverse
deb-src http://security.ubuntu.com/ubuntu trusty-security multiverse
deb http://perestroika-repo-tst.infra.mirantis.net/mos-repos/ubuntu/master/ mos-master main
"""

            with open(path_to_sources_list, 'w') as file:
                file.write(sources)
                file.close()

        cache.clear()
        cache.update()
        cache.open()

        return cache

    def prepare_apt(self, version, update_cache=False, cache_path='cache'):
        try:
            current_dir = os.getcwd()
        except:
            current_dir = './'

        path_to_cache = os.path.join(current_dir, cache_path, version)

        if update_cache:
            cache = self.prepare_cache(path_to_cache, version)
        else:
            cache = apt.cache.Cache(rootdir=path_to_cache)
            if len(cache) == 0:
                cache = self.prepare_cache(path_to_cache, version)

                if len(cache) == 0:
                    print('Cache is still empty after update. Check sources list. Aborting.')
                    sys.exit(2)

        return cache

    def get_absent_packages(self, package_name, repo_cache, debug=False):
        match = pkg_recommended_re.match(package_name)
        if match:
            pkg_name=match.group('package_name')
            pkg_version=match.group('package_version')
            try:
                cur_pkg = repo_cache[pkg_name]

                if pkg_version:
                    valid_marker = False
                    for version in cur_pkg.versions:
                        #print version.version
                        compared_versions = apt.apt_pkg.version_compare(pkg_version, version.version)
                        if args.debug:
                            print pkg_version + ' <> ' + version.version
                            print compared_versions
                        if compared_versions < 0:
                            valid_marker = True

                    if not valid_marker:  
                        print pkg_name + ' [ ' + pkg_version + ' ] ' + ' --- is absent.'
            except KeyError:
                print pkg_name + ' --- is absent.'



    def get_package_from_cache(self, repo_cache, package_name, package_version=None, secondary_cache=None):
        
        if args.debug:
            print 'Verifying: ' + package_name
        for package in repo_cache.keys():
            already_in_the_list = False
            if package == package_name:

                cur_pkg = repo_cache[package]
                if len(cur_pkg.versions) > 1:
                    print '========================='
                    print 'More than one version of package: ' + package
                    print '========================='
                    for version in cur_pkg.versions:
                        package_origin = version.origins.pop()
                        print ('%s - [%s|%s|%s|%s]' % (version.version, package_origin.component, package_origin.archive, package_origin.site, package_origin.origin))
                    print '========================='
                else:
                    package_origin = cur_pkg.versions[0]

                if hasattr(package_origin, 'source_name'):
                    package_source_name = package_origin.source_name
                else:
                    package_source_name = package_name

                for package_element in self.verified_pkg_dictionary:
                    if  package_element['Name'] == package_name:
                        already_in_the_list = True

                if not already_in_the_list:
                    self.verified_pkg_dictionary.append({'Name' : package_name, 'SourceName': package_source_name})

                for version in cur_pkg.versions:
                    if package_version and version.version != package_version:
                        continue

                    for dependencies in version.dependencies:
                        for dependency in dependencies:
                            if dependency.name:
                                already_in_the_list = False

                                if len(self.pkg_dictionary) > 0:
                                    for package_element in self.pkg_dictionary:
                                        if  package_element['Name'] == dependency.name:
                                            already_in_the_list = True

                                if not already_in_the_list:
                                    if dependency.relation:
                                        self.pkg_dictionary.append({'Name' : dependency.name, 'Relation' : dependency.relation, 'Version' : dependency.version, 'PKG_WHICH_REQUIRES': package_name})
                                    else:
                                        self.pkg_dictionary.append({'Name' : dependency.name, 'Relation' : '', 'Version' : '', 'PKG_WHICH_REQUIRES': package_name})

                                if already_in_the_list:
                                    if dependency.relation:
                                        update_dic = False
                                        package_in_dic = [d for d in self.pkg_dictionary if d['Name'] == dependency.name]
                                        package_in_dic = package_in_dic.pop()
                                        diff_result = apt.apt_pkg.version_compare(package_in_dic['Relation']+package_in_dic['Version'],dependency.relation+dependency.version)
                                        if diff_result < -1 or diff_result == 1:
                                            update_dic = True
                                        elif diff_result == 0 or diff_result > 1 or diff_result == -1:
                                            pass
                                        else:
                                            import ipdb; ipdb.set_trace()

                                        if update_dic:
                                            for dic in self.pkg_dictionary:
                                                if dic['Name'] == dependency.name:
                                                    dic_2_update = {'Name' : dependency.name, 'Relation' : dependency.relation, 'Version' : dependency.version, 'PKG_WHICH_REQUIRES': package_name}
                                                    dic.update(dic_2_update)


        if secondary_cache:
            package_found = False
            for package in secondary_cache.keys():
                if package == package_name:
                    package_found = True
                    cur_pkg = secondary_cache[package]

                    version = cur_pkg.versions[0]

                    if version:
                        package_in_dic = [d for d in self.pkg_dictionary if d['Name'] == package_name]
                        package_in_dic = package_in_dic.pop()

                        diff_result = apt.apt_pkg.version_compare(package_in_dic['Version'],version.version)

                        if diff_result == 1:
                                self.not_satisfied_pkg_dictionary.append({'Name' : package_in_dic['Name'], 'Relation' : package_in_dic['Relation'], 'Version' : package_in_dic['Version'], 'PKG_WHICH_REQUIRES': package_in_dic['PKG_WHICH_REQUIRES'], 'NA': 'False'})

            if not package_found:
                package_in_dic = [d for d in self.pkg_dictionary if d['Name'] == package_name]
                package_in_dic = package_in_dic.pop()
                self.not_satisfied_pkg_dictionary.append({'Name' : package_in_dic['Name'], 'Relation' : package_in_dic['Relation'], 'Version' : package_in_dic['Version'], 'PKG_WHICH_REQUIRES': package_in_dic['PKG_WHICH_REQUIRES'], 'NA': 'True'})

def get_pkg_uri(uri):
    if uri:
        pkg_uri_match = pkg_uri_re.match(uri)

        if pkg_uri_match:
            pkg_uri = pkg_uri_match.group()
        else:
            pkg_uri = package.uri

        return pkg_uri 

def main(args):
    packages = TrustyPackages()
    repo_cache = ''
    mos_repo_cache = ''


    if args.update_cache:
        repo_cache = packages.prepare_apt(args.distr, args.update_cache)
    else:
        repo_cache = packages.prepare_apt(args.distr)

    if args.update_cache:
        mos_repo_cache = packages.prepare_apt('mos', args.update_cache)
    else:
        mos_repo_cache = packages.prepare_apt('mos')

    if args.package_name:
        if args.package_version:
            packages.get_package_from_cache(repo_cache, args.package_name, args.package_version)
        else:
            packages.get_package_from_cache(repo_cache, args.package_name)

        for package_in_dictionary in packages.pkg_dictionary:
            packages.get_package_from_cache(repo_cache, package_in_dictionary['Name'], secondary_cache=mos_repo_cache)

        print packages.pkg_dictionary
        print packages.verified_pkg_dictionary
        print packages.not_satisfied_pkg_dictionary


    if repo_cache:
        repo_cache.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get deploy tasks by role.')
    parser.add_argument('-p', '--package_name', metavar=('PACKAGENAME'), type=str,\
                        help="Package name.")
    parser.add_argument('-v', '--package_version', metavar=('PACKAGEVERSION'), type=str,\
                        help="Package version.")
    parser.add_argument('-u', '--update-cache', action='store_true',
                        help='Force cache update')
    parser.add_argument('-m', '--distr', metavar=('DISTR'), type=str,\
                        help='Update distribution', default='debian')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Verbosity level')
    parser.add_argument('-i', '--info', action='version',
                        version='Version: 1.0')
    args = parser.parse_args()

    main(args)

