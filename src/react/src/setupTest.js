import React, {
    useState,
    useEffect,
    useContext,
    useReducer,
    useCallback,
    useMemo,
    useRef,
    useImperativeHandle,
    useLayoutEffect,
    useDebugValue
} from "react";
import { setHarnessApi } from "./index";
import { render } from '@testing-library/react';
import { createMockEnvironment } from "relay-test-utils";
import { QueryRenderer } from 'react-relay';


const environment = createMockEnvironment()

setHarnessApi({
    getEnvironment: name => {
        return environment;
    },
    currentUser: {
        userId: 1
    },
    reactHooks: {
        useState: useState,
        useEffect: useEffect,
        useContext: useContext,
        useReducer: useReducer,
        useCallback: useCallback,
        useMemo: useMemo,
        useRef: useRef,
        useImperativeHandle: useImperativeHandle,
        useLayoutEffect: useLayoutEffect,
        useDebugValue: useDebugValue
    }
})

global.queryRendererSetup = (inputQuery, componentToRender) => {


    render(
        <QueryRenderer
            environment={environment}
            query={inputQuery}
            variables={{}}
            render={({ error, props }) => {
                if (props) {
                    return componentToRender(props);
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    )
    return environment
}