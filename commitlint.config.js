// commitlint.config.js
//
// Conventional Commits enforcement for quanto.
// Consumed by the commitlint pre-commit hook on the commit-msg stage.
//
// Replaces the inline regex check from the previous lefthook.yml setup —
// same rule spirit (feat|fix|docs|...), more thorough field-by-field checks.

module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'feat',      // new feature
        'fix',       // bug fix
        'chore',     // tooling, deps, housekeeping
        'docs',      // documentation only
        'refactor',  // code change that neither fixes a bug nor adds a feature
        'test',      // adding or correcting tests
        'perf',      // performance improvement
        'ci',        // CI/CD pipeline change
        'build',     // build system / external dependencies
        'revert',    // revert a previous commit
      ],
    ],
    'type-case': [2, 'always', 'lower-case'],
    'type-empty': [2, 'never'],
    'scope-case': [2, 'always', 'lower-case'],
    'subject-case': [2, 'never', ['upper-case', 'pascal-case', 'start-case']],
    'subject-empty': [2, 'never'],
    'subject-full-stop': [2, 'never', '.'],
    'subject-max-length': [2, 'always', 72],
    'header-max-length': [2, 'always', 100],
    'body-leading-blank': [2, 'always'],
    'body-max-line-length': [2, 'always', 100],
    'footer-leading-blank': [2, 'always'],
    'footer-max-line-length': [2, 'always', 100],
  },
};
