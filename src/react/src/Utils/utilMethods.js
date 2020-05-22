import _ from "lodash";

function setAll (input, newValue) {
    Object.entries(input).map(([key, value]) => {
        if (_.isPlainObject(value)) {
            input[key] = setAll(value, newValue)
        } else {
            input[key] = newValue
        }
    })
    return input
}

export {setAll};