import { harnessApi } from "../index"


// Default Hooks
function useState(...args) {
    return harnessApi.reactHooks.useState(...args)
}

function useEffect(...args) {
    return harnessApi.reactHooks.useEffect(...args)
}

function useContext(...args) {
    return harnessApi.reactHooks.useContext(...args)
}

function useReducer(...args) {
    return harnessApi.reactHooks.useReducer(...args)
}

function useCallback(...args) {
    return harnessApi.reactHooks.useCallback(...args)
}

function useMemo(...args) {
    return harnessApi.reactHooks.useMemo(...args)
}

function useRef(...args) {
    return harnessApi.reactHooks.useRef(...args)
}

function useImperativeHandle(...args) {
    return harnessApi.reactHooks.useImperativeHandle(...args)
}

function useLayoutEffect(...args) {
    return harnessApi.reactHooks.useLayoutEffect(...args)
}

function useDebugValue(...args) {
    return harnessApi.reactHooks.useDebugValue(...args)
}

// Custom Hooks
// https://blog.logrocket.com/how-to-get-previous-props-state-with-react-hooks/
function usePrevious(val) {
    const ref = useRef();

    useEffect(() => {
        ref.current = val
    })

    return ref.current
}

export {
    useState,
    useEffect,
    useContext,
    useReducer,
    useCallback,
    useMemo,
    useRef,
    useImperativeHandle,
    useLayoutEffect,
    useDebugValue,

    usePrevious
}