<?php

include "DjangoUnitTestEngine.php";
include "JestUnitTestEngine.php";

final class DjangoJestUnitTestEngine extends ArcanistUnitTestEngine {
    public function run() {

        $djangoUnitTestEngine = new DjangoUnitTestEngine($this);

        $djangoResults = $djangoUnitTestEngine->run();

        $jestUnitTestEngine = new JestUnitTestEngine($this);

        $jestResults = $jestUnitTestEngine->run();


        return array_merge($djangoResults, $jestResults);
    }
}
