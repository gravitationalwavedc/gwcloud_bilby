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

const ha = require("../../../index");
const React = require("react");

function getContext() {
    return ha.harnessApi ? ha.harnessApi.relayContext : null;
}

module.exports = getContext;