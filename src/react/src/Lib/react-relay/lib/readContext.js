/**
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *
 *
 * @format
 */

// flowlint ambiguous-object-type:error
'use strict';

var index = require("../../../index");

function readContext(Context) {
  return index.harnessApi.readContext(Context);
}

module.exports = readContext;