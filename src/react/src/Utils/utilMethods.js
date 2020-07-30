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
// Tests if a string is a number
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

// Will merge obj2 and obj3 into obj1, with values from objects to the right overwriting objects to the left
// obj1 is modified in place
// Nulls do not overwrite
// Null object can also be input, but will do nothing
function mergeUnlessNull (obj1, obj2, obj3) {
    return _.mergeWith(obj1, obj2, obj3, (o, s) => _.isNull(s) ? o : s)
}

// This seems to work in my current timezone
// Therefore I shall infer it works everywhere
function formatDate(date, localeString) {
    const dateObject = new Date(date);
    const dateString = dateObject.toLocaleString(localeString, {hour12: false})
    
    return dateString
}

export {
    unCamelCase,
    isNumeric,
    isInteger,
    isPositive,
    mergeUnlessNull,
    formatDate
};