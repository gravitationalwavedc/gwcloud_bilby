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

// From https://stackoverflow.com/questions/4149276/how-to-convert-camelcase-to-camel-case
function unCamelCase (string) {
    return string
    // insert a space before all caps
    .replace(/([A-Z])/g, ' $1')
    // uppercase the first character
    .replace(/^./, function(str){ return str.toUpperCase(); })
}

export {setAll, unCamelCase};