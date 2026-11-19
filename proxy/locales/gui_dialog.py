"""Auto-split locale fragment: gui_dialog.  Merged by the parent module."""

EN = {
    'gui.error.title': 'Invalid Configuration',
    'gui.error.empty': '"%(label)s" cannot be empty',
    'gui.error.not_number': '"%(label)s" must be a number, got: %(value)s',
    'gui.error.invalid_number': '"%(label)s" is not a valid number: %(value)s',
    'gui.error.port_range': '"%(label)s" must be between 0 and 65535, got: %(value)s',
    'gui.dialog.switch_failed': 'Language Switch Failed',
    'gui.dialog.need_stop.title': 'Stop the Service First',
    'gui.dialog.need_stop.text': 'The service must be stopped before the certificate '
                                 'can be regenerated.',
    'gui.dialog.regen.title': 'Regenerate Certificate',
    'gui.dialog.regen.confirm': 'The current certificate will be deleted and a new one '
                                'issued. Continue?',
    'gui.dialog.delete_failed': 'Delete Failed',
    'gui.dialog.generate_failed': 'Generation Failed',
    'gui.dialog.regen.done_title': 'Done',
    'gui.dialog.regen.done': 'The certificate has been regenerated.',
    'gui.dialog.regen.done_deleted': 'The certificate has been regenerated; '
                                     'the old one was deleted.',
    'gui.dialog.cert_missing.title': 'No Certificate Yet',
    'gui.dialog.cert_missing.ask': 'There is no certificate file yet. Generate and install it now?',
    'gui.dialog.install_ok.title': 'Installed',
    'gui.dialog.install_ok.text': 'The certificate was added to the current user\'s "Trusted Root Certification '
        'Authorities".\n\n'
        'Please restart the browser (Chrome / Edge take effect immediately; Firefox\n'
        'needs a separate import under Settings -> Privacy & Security ->\n'
        'Certificates -> View Certificates).',
    'gui.dialog.install_failed': 'Installation Failed',
    'gui.dialog.unknown_error': 'Unknown error',
    'gui.dialog.no_endpoint.title': 'No Usable Address',
    'gui.dialog.no_endpoint.text': 'Set a wss port first',
    'gui.dialog.not_running.title': 'Not Running',
    'gui.dialog.not_running.text': 'Start the service first.',
    'gui.dialog.save_failed': 'Save Failed',
    'gui.dialog.reset.title': 'Restore Defaults',
    'gui.dialog.reset.ask': 'The settings in the window will be reset to their defaults '
                            '(the saved configuration file is not overwritten). Continue?',
    'gui.dialog.open_failed': 'Open Failed',
    'gui.error.password_mismatch': 'The two passwords do not match.',
    'gui.error.password_required': 'Enter a password before enabling access control.',
    'gui.error.password_short': 'The password must contain at least 4 characters.',
    'gui.error.web_auth_unreadable': 'The Web UI password file exists but cannot be read. Nothing was changed; close other copies of this program and try again.',
    'gui.confirm.title': 'Clear Access Password',
    'gui.confirm.web_password_off': 'This clears the stored Web UI password permanently. Continue?',
}

