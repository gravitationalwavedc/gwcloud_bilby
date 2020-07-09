import _ from "lodash";

// This function has not been used anywhere, so commented out currently

// function setAll (input, newValue) {
//     Object.entries(input).map(([key, value]) => {
//         if (_.isPlainObject(value)) {
//             input[key] = setAll(value, newValue)
//         } else {
//             input[key] = newValue
//         }
//     })
//     return input
// }

// From https://stackoverflow.com/questions/4149276/how-to-convert-camelcase-to-camel-case
function unCamelCase (string) {
    return string
    // insert a space before all caps
    .replace(/([A-Z])/g, ' $1')
    // uppercase the first character
    .replace(/^./, function(str){ return str.toUpperCase(); })
}

// Based on my tests, this answer on SO is good and simple
// https://stackoverflow.com/a/52986361
function isNumeric (num) {
    return (!isNaN(parseFloat(num)) && isFinite(num))
}

function isInteger (num) {
    return (Number.isInteger(Number.parseFloat(num)))
}

function isPositive (num) {
    return (Number.parseFloat(num) > 0)
}

export {
    unCamelCase,
    isNumeric,
    isInteger,
    isPositive
};