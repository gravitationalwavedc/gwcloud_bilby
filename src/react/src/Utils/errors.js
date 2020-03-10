
const assembleErrorString = (errors) => {
    let prefix = 'Must be '
    if (errors.length === 1) {
        return prefix + errors[0]
    } else {
        const last = errors.pop()
        return prefix + errors.join(', ') + ' and ' + last
    }
}

const checkForErrors = (...fns) => (data) => fns.reduceRight((y, f) => f(y), {data: data, errors: []}).errors

const longerThan = threshold => ({data, errors}) => {
    if (data.length < threshold) {
        errors.push('longer than ' + threshold + ' characters')
    }
    return {data, errors}
}

const shorterThan = threshold => ({data, errors}) => {
    if (data.length > threshold) {
        errors.push('shorter than ' + threshold + ' characters')
    }
    return {data, errors}
}

const isNumber = ({data, errors}) => {
    if (isNaN(data)) {
        errors.push('a number')
    }
    return {data, errors}
}

const smallerThan = (threshold, name) => ({data, errors}) => {
    if (data > threshold) {
        errors.push('smaller than ' + name)
    }
    return {data, errors}
}



export {
    checkForErrors,
    assembleErrorString,
    longerThan,
    shorterThan,
    isNumber,
    smallerThan,
}