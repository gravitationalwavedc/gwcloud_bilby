import React from "react";
import {harnessApi} from "../index";
import { graphql, commitMutation } from "react-relay";
import { List } from "semantic-ui-react";

const assembleErrorString = (errors) => {
    let prefix = 'Must'
    if (errors.length === 1) {
        return prefix + " " + errors[0]
    } else {
        // const last = errors.pop()
        // return prefix + errors.join(', ') + ' and ' + last
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

const checkForErrors = (...fns) => (data) => fns.reduceRight((y, f) => f(y), {data: data, errors: []}).errors

const longerThan = threshold => ({data, errors}) => {
    if (data.length < threshold) {
        errors.push('be longer than ' + threshold + ' characters')
    }
    return {data, errors}
}

const shorterThan = threshold => ({data, errors}) => {
    if (data.length > threshold) {
        errors.push('be shorter than ' + threshold + ' characters')
    }
    return {data, errors}
}

const isNumber = ({data, errors}) => {
    if (isNaN(data)) {
        errors.push('be a number')
    }
    return {data, errors}
}

const smallerThan = (threshold, name) => ({data, errors}) => {
    if (data >= threshold) {
        errors.push('be smaller than ' + name)
    }
    return {data, errors}
}

const notEmpty = ({data, errors}) => {
    if (data.trim() === "") {
        errors.push('not be empty')
    }
    return {data, errors}
}

const noneFalse = (otherBools) => ({data, errors}) => {
    otherBools.push(data)
    if (!otherBools.some((e) => e === true)) {
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

const validJobName = ({data, errors}) => {
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
    longerThan,
    shorterThan,
    isNumber,
    smallerThan,
    notEmpty,
    noneFalse,
    nameUnique,
    validJobName
}