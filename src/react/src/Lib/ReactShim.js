// Import the original react module - this will work because we explicitly exclude this file from being replaced by the Module Replace Webpack Plugin in the webpack config.
const React = require("react");

// Next we import the index module where the harnessApi variable is stored - note that we don't immediately declare .harnessApi here, because when this file is loaded,
// the reference to the harnessApi is null, so we must use index.harnessApi later on to get the real value
const index = require("../index")

// Next copy the React module in to a new object so we can replace the hook functions
const NewReact = {
    ...React
}

// Now we replace the hook functions
// Default Hooks
NewReact.useState = (...args) => {
    return index.harnessApi.reactHooks.useState(...args)
}

NewReact.useEffect = (...args) => {
    return index.harnessApi.reactHooks.useEffect(...args)
}

NewReact.useContext = (...args) => {
    return index.harnessApi.reactHooks.useContext(...args)
}

NewReact.useReducer = (...args) => {
    return index.harnessApi.reactHooks.useReducer(...args)
}

NewReact.useCallback = (...args) => {
    return index.harnessApi.reactHooks.useCallback(...args)
}

NewReact.useMemo = (...args) => {
    return index.harnessApi.reactHooks.useMemo(...args)
}

NewReact.useRef = (...args) => {
    return index.harnessApi.reactHooks.useRef(...args)
}

NewReact.useImperativeHandle = (...args) => {
    return index.harnessApi.reactHooks.useImperativeHandle(...args)
}

NewReact.useLayoutEffect = (...args) => {
    return index.harnessApi.reactHooks.useLayoutEffect(...args)
}

NewReact.useDebugValue = (...args) => {
    return index.harnessApi.reactHooks.useDebugValue(...args)
}

module.exports = NewReact;