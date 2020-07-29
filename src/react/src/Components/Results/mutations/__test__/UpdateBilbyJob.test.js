import React from "react";
import { MockPayloadGenerator, createMockEnvironment } from "relay-test-utils";

import { expect } from "@jest/globals";
import '@testing-library/jest-dom/extend-expect';
import UpdateBilbyJob from "../UpdateBilbyJob";
import { setHarnessApi } from "../../../..";


test('Mutation should send correctly', () => {
    const environment = createMockEnvironment()

    setHarnessApi({
        getEnvironment: name => {
            return environment;
        },
        currentUser: {
            userId: 1
        }
    })

    
    const mockCallback = jest.fn()

    UpdateBilbyJob(
        {
            jobId: 1,
            private: true
        },
        mockCallback
    )

    const operation = environment.mock.getMostRecentOperation();

    expect(operation.root.variables.jobId).toBe(1)
    expect(operation.root.variables.private).toBe(true)

    environment.mock.resolve(
        operation,
        MockPayloadGenerator.generate(operation, {
            String() {
                return 'Success Message!'
            }
        })
    );
    
    expect(mockCallback).toBeCalled()
    expect(mockCallback.mock.calls[0][0]).toBe(true)
    expect(mockCallback.mock.calls[0][1]).toBe('Success Message!')
})