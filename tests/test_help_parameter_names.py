# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import argparse
import copy
from contextlib import redirect_stdout
from io import StringIO
import unittest

from knack.help import CommandHelpFile, HelpAuthoringException, HelpParameter
from tests.util import DummyCLI


class TestHelpParameterNames(unittest.TestCase):

    def setUp(self):
        from knack.invocation import CommandInvoker
        cli_ctx = DummyCLI()
        cli_ctx.invocation = CommandInvoker(cli_ctx)
        self.help_ctx = cli_ctx.invocation.help

    @staticmethod
    def _parser():
        parser = argparse.ArgumentParser(prog='test copy')
        parser.add_argument('--source', '-s', help='Original source')
        parser.add_argument('--source-path', help='Original path')
        parser.add_argument('destination', metavar='destination file', help='Original destination')
        return parser

    def _render(self, parameters):
        parser = self._parser()
        # Use the public renderer and the same YAML decoder as authored help files.
        import yaml
        parser.help_file = yaml.safe_dump({'parameters': parameters})
        output = StringIO()
        with redirect_stdout(output):
            self.help_ctx.show_help('test', ['copy'], parser, False)
        return output.getvalue()

    def test_alias_names_render_authored_help(self):
        for name in ['--source', '-s', '-s --source', '--source -s']:
            with self.subTest(name=name):
                output = self._render([{
                    'name': name, 'short-summary': 'Authored source',
                    'long-summary': 'More source details',
                    'populator-commands': ['test sources']
                }])
                self.assertIn('Authored source.', output)
                self.assertIn('More source details.', output)
                self.assertIn('Values from: test sources.', output)
                self.assertIn('--source -s', output)
                self.assertNotIn('Original source.', output)
                self.assertIn('--source-path', output)
                self.assertIn('Original path.', output)

    def test_exact_match_precedes_alias_regardless_of_entry_order(self):
        exact = {'name': '--source -s', 'short-summary': 'Exact summary'}
        alias = {'name': '--source', 'short-summary': 'Alias summary'}
        for entries in [[alias, exact], [exact, alias]]:
            with self.subTest(entries=entries):
                output = self._render(entries)
                self.assertIn('Exact summary.', output)
                self.assertNotIn('Alias summary.', output)

    def test_unrelated_and_partial_names_do_not_override_help(self):
        for name in ['--sour', 'source', '--source-path -s', '--source --unknown',
                     '--source -s extra', '--source -s -s', 'destination',
                     'file destination', 'destination file extra']:
            with self.subTest(name=name):
                output = self._render([{'name': name, 'short-summary': 'Wrong summary'}])
                self.assertNotIn('Wrong summary.', output)
                self.assertIn('Original source.', output)
                self.assertIn('Original destination.', output)

    def test_positional_name_with_spaces_is_exact(self):
        output = self._render([{'name': 'destination file', 'short-summary': 'Authored destination'}])
        self.assertIn('destination file', output)
        self.assertIn('Authored destination.', output)

    def test_loading_does_not_modify_authored_data_or_canonical_names(self):
        data = {'parameters': [{'name': '-s --source', 'short-summary': 'Authored source'}]}
        original = copy.deepcopy(data)
        help_file = CommandHelpFile(self.help_ctx, 'copy', self._parser())
        names = [p.name for p in help_file.parameters]
        help_file._load_from_data(data)  # pylint: disable=protected-access
        self.assertEqual(data, original)
        self.assertEqual([p.name for p in help_file.parameters], names)
        self.assertEqual(help_file.parameters[1].short_summary, 'Authored source.')

    def test_direct_update_accepts_only_single_alias_or_complete_alias_list(self):
        for name in ['--source', '-s', '--src', '-s --src --source', '--source --src -s']:
            with self.subTest(name=name):
                parameter = HelpParameter(['--source', '-s', '--src'], 'Original', False)
                data = {'name': name, 'type': 'integer', 'short-summary': 'Updated'}
                original = copy.deepcopy(data)
                parameter.update_from_data(data)
                self.assertEqual(parameter.short_summary, 'Updated.')
                self.assertEqual(parameter.type, 'integer')
                self.assertEqual(parameter.name, '--source --src -s')
                self.assertEqual(data, original)

    def test_direct_update_rejects_invalid_names(self):
        for name in [None, '', 1, ['--source'], '--sour', 'source',
                     '--source -s', '--source --unknown -s', '--source --src -s -s']:
            with self.subTest(name=name):
                parameter = HelpParameter(['--source', '-s', '--src'], 'Original', False)
                with self.assertRaises(HelpAuthoringException):
                    parameter.update_from_data({'name': name, 'short-summary': 'Wrong'})
                self.assertEqual(parameter.short_summary, 'Original.')

    def test_direct_update_preserves_positional_name_boundaries(self):
        parameter = HelpParameter(['source file'], 'Original', False)
        for name in ['source', 'file', 'file source']:
            with self.subTest(name=name), self.assertRaises(HelpAuthoringException):
                parameter.update_from_data({'name': name})
        parameter.update_from_data({'name': 'source file', 'short-summary': 'Updated'})
        self.assertEqual(parameter.short_summary, 'Updated.')

    def test_dash_prefixed_positional_metavars_match_exactly(self):
        import yaml
        for metavar in ['-FILE', '--input', '-FILE -OTHER']:
            for name in [metavar, ' ' + metavar + ' ', ' '.join(reversed(metavar.split()))]:
                with self.subTest(metavar=metavar, name=name):
                    parser = self._parser()
                    parser.add_argument('input_file', metavar=metavar, help='Original input')
                    parser.help_file = yaml.safe_dump({'parameters': [
                        {'name': name, 'short-summary': 'Authored input'}
                    ]})
                    output = StringIO()
                    with redirect_stdout(output):
                        self.help_ctx.show_help('test', ['copy'], parser, False)
                    if name == metavar:
                        self.assertIn('Authored input.', output.getvalue())
                    else:
                        self.assertNotIn('Authored input.', output.getvalue())
                        self.assertIn('Original input.', output.getvalue())
                    help_file = CommandHelpFile(self.help_ctx, 'copy', parser)
                    parameter = next(p for p in help_file.parameters if p.name == metavar)
                    if name == metavar:
                        parameter.update_from_data({'name': name})
                    else:
                        with self.assertRaises(HelpAuthoringException):
                            parameter.update_from_data({'name': name})

    def test_deprecated_and_current_alias_groups_remain_separate(self):
        from knack.arguments import CLICommandArgument
        from knack.deprecation import Deprecated
        from knack.parser import CLICommandParser
        cli_ctx = self.help_ctx.cli_ctx
        parser = self._parser()
        deprecated = Deprecated(cli_ctx, target='--old-source', redirect='--current')
        argument = CLICommandArgument('current', options_list=['--current', '-c', deprecated],
                                      help='Original grouped')
        CLICommandParser._add_argument(parser, argument)  # pylint: disable=protected-access
        data = {'parameters': [
            {'name': '-c', 'short-summary': 'Current summary'},
            {'name': '--old-source', 'short-summary': 'Deprecated summary'}
        ]}
        help_file = CommandHelpFile(self.help_ctx, 'copy', parser)
        help_file._load_from_data(data)  # pylint: disable=protected-access
        current = next(p for p in help_file.parameters if p.name == '--current -c')
        old = next(p for p in help_file.parameters if p.name == '--old-source')
        self.assertEqual(current.short_summary, 'Current summary.')
        self.assertEqual(old.short_summary, 'Deprecated summary.')
        self.assertIsNotNone(old.deprecate_info)
        for parameter, name in [(current, '--old-source'), (old, '--current'),
                                (current, '--current -c --old-source')]:
            with self.subTest(name=name), self.assertRaises(HelpAuthoringException):
                parameter.update_from_data({'name': name})


if __name__ == '__main__':
    unittest.main()
