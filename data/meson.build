# FreeDesktop Desktop File
desktop_conf = configuration_data()
desktop_conf.set('icon', application_id)
desktop_file = i18n.merge_file(
  input: configure_file(
    input: 'org.gnome.gitlab.somas.Apostrophe.desktop.in.in',
    output: '@BASENAME@',
    configuration: desktop_conf
  ),
  output: '@0@.desktop'.format(application_id),
  po_dir: podir,
  type: 'desktop',
  install: true,
  install_dir: get_option('datadir') / 'applications'
)

# Validate Desktop File
desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test (
    'Validate desktop file',
    desktop_file_validate,
    args: desktop_file.full_path()
  )
endif

# Freedesktop AppData File
appdata_conf = configuration_data()
appdata_conf.set('app-id', application_id)
appdata_conf.set('gettext-package', gettext_package)

metainfo_configured = configure_file(
    input: 'org.gnome.gitlab.somas.Apostrophe.metainfo.xml.in',
    output: 'configured' + '@BASENAME@',
    configuration: appdata_conf
)

appdata_file = i18n.merge_file(
  input: metainfo_configured,
  output: '@0@.metainfo.xml'.format(application_id),
  po_dir: podir,
  install: true,
  install_dir: get_option('datadir') / 'metainfo'
)

# Validate AppData File
appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test (
    'validate-appdata',
    appstreamcli,
    args: ['validate', '--no-net', '--explain', appdata_file.full_path()],
    workdir: meson.current_build_dir()
  )
endif

# Gschema
install_data(
	'org.gnome.gitlab.somas.Apostrophe.gschema.xml',
	install_dir:  get_option('datadir') / 'glib-2.0' / 'schemas',
	rename: '@0@.gschema.xml'.format(application_id)
)

# Resources
ui_config = configuration_data()
ui_config.set('app-id', application_id)
ui_config.set('version', meson.project_version() + version_suffix)
ui_config.set('package_url', 'https://apps.gnome.org/Apostrophe/')
ui_preconfigured_files = files(
  'ui/About.ui.in'
)
ui_dependencies = []
foreach ui_file: ui_preconfigured_files
  ui_dependencies += configure_file(
    input:  ui_file,
    output: '@BASENAME@',
    configuration: ui_config
  )
endforeach

# D-Bus service file
service_conf = configuration_data()
service_conf.set('app-id', application_id)
service_conf.set('bindir', bindir)
configure_file(
  input: 'org.gnome.gitlab.somas.Apostrophe.service.in',
  output: '@0@.service'.format(application_id),
  install: true,
  install_dir: get_option('datadir') / 'dbus-1' / 'services',
  configuration: service_conf
)

message('datadir')
message(datadir)
subdir('icons')
subdir('styles')

install_subdir(
	'lua',
	install_dir: pkgdatadir
)

install_subdir(
	'media',
	exclude_directories: ['css/gtk', 'icons'],
	exclude_files: ['apostrophe_markdown.md'],
	install_dir: pkgdatadir
)

install_subdir(
	'pandoc_templates',
	install_dir: pkgdatadir
)


install_subdir(
	'reference_files',
	install_dir: pkgdatadir
)

resources = gnome.compile_resources(
  meson.project_name(),
  meson.project_name() + '.gresource.xml',
  gresource_bundle: true,
  install:true,
  install_dir: pkgdatadir,
  dependencies: [ui_dependencies]
)
