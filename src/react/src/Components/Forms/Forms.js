import React from "react";
import _ from "lodash";
import { Form, Header, Grid, Segment, Item } from "semantic-ui-react";
import { useEffect, useReducer, useContext, useState } from "../../Utils/hooks";
import {setAll} from "../../Utils/utilMethods"
import { assembleErrorString } from "../../Utils/errors";

function reducer(state, action) {
    switch (action.type) {
        case 'SET_FIELD_VALUE':
            const newValues = _.cloneDeep(state.values)
            _.forIn(action.payload, (value, key) => {
                _.set(newValues, key, value)
            })
            return {...state, values: newValues}

        case 'SET_FIELD_TOUCHED':
            const newTouched = _.cloneDeep(state.touched)
            _.forIn(action.payload, (value, key) => {
                _.set(newTouched, key, value)
            })
            return {...state, touched: newTouched}

        case 'SET_FIELD_VISIBLE':
            const newVisible = _.cloneDeep(state.visible)
            _.forIn(action.payload, (value, key) => {
                _.set(newVisible, key, value)
            })
            return {...state, visible: newVisible}

        case 'SET_ERRORS':
            return {
                ...state,
                errors: action.payload
            }

        case 'SUBMIT_ATTEMPT':
            return {
                ...state,
                isSubmitting: true,
                touched: setAll(state.values, true)
            }

        case 'SUBMIT_SUCCESS':
            return {
                ...state,
                isSubmitting: false,
            }
            
        case 'SUBMIT_FAILURE':
            return {
                ...state,
                isSubmitting: false,
            }
        default:
            return state
    }
}

function useFormControl(props) {
    const [state, dispatch] = useReducer(reducer,
        {
            values: props.initialValues,
            errors: {},
            touched: {},
            visible: setAll(props.initialValues, true),
            isSubmitting: false
        }
    )

    useEffect(() => {
        if (props.validate) {
            const errors = props.validate(state.values)
            dispatch({type: 'SET_ERRORS', payload: errors})
        }
    }, [state.values])

    const handleChange = fieldName => (event, data) => {
        const value = data.type === 'checkbox' ? data.checked : data.value
        var linkedVals = {}
        
        if (props.linkedValues) {
            linkedVals = props.linkedValues(fieldName, value, state.values)
        }

        dispatch({
            type: 'SET_FIELD_VALUE',
            payload: ({ ...linkedVals, [fieldName]: value })
        })
    }

    const handleBlur = (fieldName) => event => {
        const linkedTouched = {}

        if (props.linkedErrors && props.linkedErrors[fieldName]) {
            props.linkedErrors[fieldName].forEach(name => linkedTouched[name] = true)
        }

        dispatch({
            type: 'SET_FIELD_TOUCHED',
            payload: ({ ...linkedTouched, [fieldName]: true })
        })
    }

    const handleSubmit = () => {
        dispatch({type: 'SUBMIT_ATTEMPT'})
        const errors = props.validate ? props.validate(state.values) : {}
        if (_.isEmpty(errors)) {
            props.onSubmit(state.values)
            dispatch({type: 'SUBMIT_SUCCESS'})
            return true
        } else {
            dispatch({type: 'SET_ERRORS', payload: errors})
            dispatch({type: 'SUBMIT_FAILURE'})
            return false
        }
    }

    const handleVisible = fieldName => visible => {
        dispatch({type: 'SET_FIELD_VISIBLE', payload: {[fieldName]: visible}})
    }

    const getFieldProps = (fieldName) => ({
        value: _.get(state.values, fieldName),
        error: _.get(state.errors, fieldName),
        touched: _.get(state.touched, fieldName),
        handleVisible: handleVisible(fieldName),
        onChange: handleChange(fieldName),
        onBlur: handleBlur(fieldName)
    })

    return { handleSubmit, getFieldProps, ...state }
}

const FormControlContext = React.createContext({})


function FormController(props) {
    const formProps = useFormControl(props)
    const {values, handleSubmit} = formProps
    return (
        <FormControlContext.Provider value={formProps}>
            {props.children({values, handleSubmit})}
        </FormControlContext.Provider>
    )
}

function useField(fieldName) {
    const {getFieldProps} = useContext(FormControlContext)
    const {handleVisible, touched, ...fieldProps} = getFieldProps(fieldName)

    useEffect(() => {
        handleVisible(true)
        return () => handleVisible(false)
    }, [])

    fieldProps.error = (touched && fieldProps.error) ? {content: assembleErrorString(fieldProps.error), pointing: "above"} : false

    return fieldProps
}

function InputField(props) {
    const {name, ...formProps} = props
        const fieldProps = useField(name)


    return (
        <Form.Input
            id={name}
            {...formProps}
            {...fieldProps}
        />
        
    )
}

function TextField(props) {
    const {name, ...formProps} = props
        const fieldProps = useField(name)

    return (
        <Form.TextArea
            id={name}
            {...formProps}
            {...fieldProps}
        />
        
    )
}

function CheckboxField(props) {
    const {name, ...formProps} = props
    const {value, interacted, ...fieldProps} = useField(name)

    return (
        <Form.Checkbox
            id={name}
            {...formProps}
            {...fieldProps}
            checked={value}
        />
        
    )
}

function SelectField(props) {
    const {name, ...formProps} = props
    const fieldProps = useField(name)
    
    return <Form.Select
        id={name}
        {...formProps}
        {...fieldProps}
    />
}

function FormSegment(props) {
    const {header, subheader, children} = props
    return (
        <Segment color='black' as={Grid} verticalAlign='middle' columns={2}>
            <Grid.Row>
                <Grid.Column width={5}>
                    <Header content={header} subheader={subheader}/>
                </Grid.Column>
                <Grid.Column width={11} as={Grid}>
                    {children}
                </Grid.Column>
            </Grid.Row>
        </Segment>
    )
}

export { FormController, InputField, TextField, CheckboxField, SelectField, FormSegment }