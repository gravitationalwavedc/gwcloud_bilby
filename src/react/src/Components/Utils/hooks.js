import { useRef, useEffect } from "react";

// https://blog.logrocket.com/how-to-get-previous-props-state-with-react-hooks/
function usePrevious(val) {
    const ref = useRef();

    useEffect(() => {
        ref.current = val
    })

    return ref.current
}

export {
    usePrevious
}