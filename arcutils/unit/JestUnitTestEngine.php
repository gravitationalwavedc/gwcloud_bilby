<?php

final class JestUnitTestEngine {
    private $unitTestBase;
    public function __construct($unitTestBase)
    {
        $this->unitTestBase = $unitTestBase;
    }

    public function getEngineConfigurationName() {
        return 'jest';
    }

    protected function supportsRunAllTests() {
        return true;
    }

    public function shouldEchoTestResults() {
        return false;
    }

    public function run() {
        chdir($this->unitTestBase->getWorkingCopy()->getProjectRoot() . "/src/react/");

        $future = $this->buildTestFuture();
        list($err, $stdout, $stderr) = $future->resolve();

        // If we are running coverage the output includes a visual (non-JSON) representation
        // If that exists then exclude it before parsing the JSON.
        $json_start_index = strpos($stdout, '{"success"');
        $json_string = substr($stdout, $json_start_index);

        try {
            $json_result = phutil_json_decode($json_string);
        } catch (PhutilJSONParserException $ex) {
            $cmd = $this->command;
            throw new CommandException(
                pht(
                    "JSON command '%s' did not produce a valid JSON object on stdout: %s",
                    $cmd,
                    $stdout
                ),
                $cmd,
                0,
                $stdout,
                $stderr
            );
        }
        $test_results = $this->parseTestResults($json_result);

        // getEnableCoverage() returns either true, false, or null
        // true and false means it was explicitly turned on or off.  null means use the default
        if ($this->unitTestBase->getEnableCoverage() !== false) {
            $coverage = $this->readCoverage(
                './coverage/clover.xml'
            );
            foreach ($test_results as $test_result) {
                $test_result->setCoverage($coverage);
            }
        }

        return $test_results;
    }

    public function buildTestFuture() {
        $this->command = './node_modules/.bin/jest test --env=jsdom --json';

        // getEnableCoverage() returns either true, false, or null
        // true and false means it was explicitly turned on or off.  null means use the default
        if ($this->unitTestBase->getEnableCoverage() !== false) {
            $this->command .= ' --coverage';
        }

        return new ExecFuture('%C', $this->command);
    }

    public function parseTestResults($json_result) {
        $results = array();

        foreach ($json_result['testResults'] as $test_result) {
            $duration_in_seconds = ($test_result['endTime'] - $test_result['startTime']) / 1000;
            $status_result = $test_result['status'] === 'passed' ?
                ArcanistUnitTestResult::RESULT_PASS :
                ArcanistUnitTestResult::RESULT_FAIL;

            $result = new ArcanistUnitTestResult();
            $result->setName($test_result['name']);
            $result->setResult($status_result);
            $result->setDuration($duration_in_seconds);
            $result->setUserData($test_result['message']);
            $results[] = $result;
        }
        return $results;
    }

    /**
     * Read the coverage from a jest generated clover report
     *
     * Based on https://secure.phabricator.com/diffusion/ARC/browse/master/src/unit/parser/ArcanistPhpunitTestResultParser.php
     * More info about result: https://secure.phabricator.com/book/phabricator/article/arcanist_coverage/
     *
     * @return array
     */
    private function readCoverage($coverage_file) {
        $test_results = Filesystem::readFile($coverage_file);
        if (empty($test_results)) {
            return array();
        }

        $coverage_dom = new DOMDocument();
        $coverage_dom->loadXML($test_results);

        $reports = array();
        $files = $coverage_dom->getElementsByTagName('file');

        foreach ($files as $file) {
            $file_path = $file->getAttribute('path');
            // get total line count in file
            $line_count = count(file($file_path));

            $coverage = '';
            $any_line_covered = false;
            $start_line = 1;
            $lines = $file->getElementsByTagName('line');

            $coverage = str_repeat('N', $line_count);
            foreach ($lines as $line) {
                if ($line->getAttribute('type') != 'stmt') {
                    continue;
                }
                if ((int)$line->getAttribute('count') > 0) {
                    $is_covered = 'C';
                    $any_line_covered = true;
                } else {
                    $is_covered = 'U';
                }
                $line_no = (int)$line->getAttribute('num');
                $coverage[$line_no - 1] = $is_covered;
            }

            // Sometimes the Clover coverage gives false positives on uncovered lines
            // when the file wasn't actually part of the test. This filters out files
            // with no coverage which helps give more accurate overall results.
            if ($any_line_covered) {
                // The result should be relative paths, so convert to that (from absolute)
                $len = strlen($this->unitTestBase->getWorkingCopy()->getProjectRoot().DIRECTORY_SEPARATOR);
                $relative_path = substr($file_path, $len);
                $reports[$relative_path] = $coverage;
            }
        }
        return $reports;
    }
}