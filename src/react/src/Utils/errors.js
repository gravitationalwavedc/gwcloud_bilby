import React from "react";
import {harnessApi} from "../index";
import { graphql, commitMutation } from "react-relay";
import { List } from "semantic-ui-react";
import { isNumeric, isInteger, isPositive } from "./utilMethods";
import _ from "lodash";

// This should be fixed so that it only ever returns a string or Fragment, not either.
const assembleErrorString = (errors) => {
    let prefix = 'Must'
    if (errors.length === 1) {
        return prefix + " " + errors[0]
    } else {
        const bullets = errors.map((error, index) => <List.Item key={index} content={error}/>)
        return (
            <React.Fragment>
                {prefix + ":"}
                <List bulleted>
                    {bullets}
                </List>
            </React.Fragment>
        )
    }
}


// If error function returns an error, adds to errors object, otherwise does nothing
function errorHelper(fieldName, errorFunction, values, errors) {
    const err = errorFunction(_.get(values, fieldName))
    if (err && err.length) {
        _.set(errors, fieldName, err)
    }
}

const checkForErrors = (...fns) => (data) => fns.reduceRight((y, f) => f(y), {data: data, errors: []}).errors

const createValidationFunction = (errorFunctions, values) => {
    const errors = {}
    _.forIn(errorFunctions, (errorFunction, name) => {
        errorHelper(name, checkForErrors(...errorFunction), values, errors)
    })
    return errors
}

const isLongerThan = threshold => ({data, errors}) => {
    if (data.length < threshold) {
        errors.push('be longer than ' + threshold + ' characters')
    }
    return {data, errors}
}

const isShorterThan = threshold => ({data, errors}) => {
    if (data.length > threshold) {
        errors.push('be shorter than ' + threshold + ' characters')
    }
    return {data, errors}
}


const isANumber = ({data, errors}) => {
    if (!isNumeric(data)) {
        errors.push('be a number')
    }
    return {data, errors}
}

const isAPositiveNumber = ({data, errors}) => {
    if (!isNumeric(data) || !isPositive(data)) {
        errors.push('be a positive number')
    }
    return {data, errors}
}

const isAnInteger = ({data, errors}) => {
    if (!isNumeric(data) || !isInteger(data)) {
        errors.push('be an integer')
    }
    return {data, errors}
}

const isAPositiveInteger = ({data, errors}) => {
    if (!isNumeric(data) || !(isInteger(data) && isPositive(data))) {
        errors.push('be a positive integer')
    }
    return {data, errors}
}

const isLargerThan = (threshold, name=null) => ({data, errors}) => {
    if (_.toNumber(data) <= _.toNumber(threshold)) {
        errors.push('be larger than ' + (name ? name : threshold))
    }
    return {data, errors}
}

const isSmallerThan = (threshold, name=null) => ({data, errors}) => {
    if (_.toNumber(data) >= _.toNumber(threshold)) {
        errors.push('be smaller than ' + (name ? name : threshold))
    }
    return {data, errors}
}

const isNotEmpty = ({data, errors}) => {
    if (data.trim() === "") {
        errors.push('not be empty')
    }
    return {data, errors}
}

const hasNoneFalse = (otherBools) => ({data, errors}) => {
    const boolArray = [...otherBools, data]
    if (!boolArray.some((e) => e === true)) {
        errors.push('have at least one checked')
    }
    return {data, errors}
}


const nameUnique = ({data, errors}) => {
    commitMutation(harnessApi.getEnvironment("bilby"), {
        mutation: graphql`mutation errorsNameUniqueMutation($input: UniqueNameMutationInput!)
            {
              isNameUnique(input: $input) 
              {
                result
              }
            }`,
        variables: {
            input: {
                name: data
            }
        },
        onCompleted: (response, errors) => {
            console.log(response)
        },
    })
    return {data, errors}
}

const isValidJobName = ({data, errors}) => {
    // Matches case insensitive alphabet, number, underscore and hyphen
    let re = /^[0-9a-z\_\-]+$/i

    if (!re.test(data)) {
        errors.push("contain only letters, numbers, underscores and hyphens")
    }

    return {data, errors}
}

export {
    checkForErrors,
    assembleErrorString,
    createValidationFunction,
    isLongerThan,
    isShorterThan,
    isANumber,
    isAPositiveNumber,
    isAnInteger,
    isAPositiveInteger,
    isLargerThan,
    isSmallerThan,
    isNotEmpty,
    hasNoneFalse,
    isValidJobName
}