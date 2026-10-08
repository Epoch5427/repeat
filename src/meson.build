pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'repeat'
gnome = import('gnome')
python = import('python')

# --- Blueprint setup ---
blueprint_compiler = find_program('blueprint-compiler', required: true)

# Add your .blp files here
blueprint_sources = files(
  'UI/shortcuts-dialog.blp',
  'UI/window.blp',
)

# Compile .blp → .ui
ui_files = custom_target('ui',
  input: blueprint_sources,
  output: [
    'shortcuts-dialog.ui',
    'window.ui',
  ],
  command: [
    blueprint_compiler,
    'batch-compile',
    '@OUTDIR@',
    meson.current_source_dir() / 'UI',
    '@INPUT@',
  ],
)
# --- end Blueprint setup ---

gnome.compile_resources('repeat',
  'repeat.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  source_dir: [
    meson.current_source_dir(),          # Looks in src/
    meson.current_build_dir(),           # Looks in build/src/ (for window.ui)
    meson.project_build_root() / 'data', # Looks in build/data/ (for metainfo.xml)
  ],
  dependencies: [
    ui_files,
    appstream_file,                      # Ensures metainfo is generated first
  ],
)

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'repeat.in',
  output: 'repeat',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

repeat_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'emulator.py',
  'macro_parser.py',
  'models.py',
  'portals.py',
  'tray_indicator.py',
  'worker.py',
]

install_data(repeat_sources, install_dir: moduledir)

ui_sources = [
  'UI/__init__.py',
  'UI/macro_recorder.py',
  'UI/key_picker.py',
  'UI/coordinate_picker.py',
]

install_data(ui_sources, install_dir: moduledir / 'UI')