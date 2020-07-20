import React from "react";
import _ from "lodash";
import { Form, Grid, Label } from "semantic-ui-react";
import { assembleErrorString } from "../../Utils/errors";



class FormController extends React.Component {
    constructor(props) {
        super(props);

        const initialErrors = {}
        Object.keys(this.props.initialValues).map((key) => {
            initialErrors[key] = []
        })

        const initialVisible = {}
        Object.keys(this.props.initialValues).map((key) => {
            initialVisible[key] = true
        })

        this.state = {
            values: this.props.initialValues || {},
            errors: initialErrors,
            visible: initialVisible,
            touched: {},
            isValid: false
        }
    }

    componentDidupdate(prevProps) {
        if ((this.props.validating !== prevProps.validating) && (this.props.validating)) {
            this.setValid()
        }
    }

    handleChange = (values, errors) => {
        this.setState(prevState => ({
            values: {
                ...prevState.values,
                ...values
            },
            errors: {
                ...prevState.errors,
                ...errors
            }
        }), () => this.setValid())
    }

    handleVisibility = (name, visible) => {
        this.setState(prevState => ({
            visible: {
                ...prevState.visible,
                [name]: visible
            }
        }))
    }

    setValid = () => {
        const notEmpty = (arr) => { return Boolean(arr && arr.length) }
        const visibleErrors = _.pick(this.state.errors, Object.keys(_.pickBy(this.state.visible, val => val)))

        this.setState({
            isValid: !Object.values(visibleErrors).some(notEmpty)
        }, () => this.props.onValid(this.state.isValid, this.state.values))
    }

    render() {
        return this.props.children({
            values: this.state.values,
            errors: this.state.errors,
            validating: this.props.validating,
            handleChange: this.handleChange,
            handleVisibility: this.handleVisibility,
            setValid: this.setValid,
            setInitial: this.setInitial
        })
    }
}


class FormField extends React.Component {

    static defaultProps = {
        visible: true,
        required: true,
        valFunc: () => { },
        errFunc: () => []
    }

    componentDidMount() {
        const { name, visible, values, handleVisibility, handleChange } = this.props
        const [updatedValues, errors] = this._handleInitialValuesAndSettingErrors(name, values[name])

        handleVisibility(name, visible)
        handleChange(updatedValues, errors)
    }

    componentDidUpdate(prevProps) {
        const { name, visible, handleVisibility } = this.props

        if (visible !== prevProps.visible) {
            handleVisibility(name, visible)
        }
    }

    handleChange = (e, data) => {
        const value = data.type === 'checkbox' ? data.checked : data.value
        const { name } = data

        const [values, errors] = this._handleUpdatingValuesAndSettingErrors(name, value)

        this.props.handleChange(values, errors)
    }

    _handleInitialValuesAndSettingErrors(name, value) {
        const { errFunc, linkedErrors, valFunc } = this.props

        const values = {
            ...valFunc(value)
        }

        const errors = {
            [name]: errFunc(value),
            ...(_.mapValues(linkedErrors, (linkedErrFunc, linkedErrName) => linkedErrFunc(value)(this.props.values[linkedErrName])))
        }

        return [values, errors]
    }

    _handleUpdatingValuesAndSettingErrors(name, value) {
        let [values, errors] = this._handleInitialValuesAndSettingErrors(name, value)
        values = {
            [name]: value,
            ...values
        }

        return [values, errors]
    }

    render() {
        const { label, name, form, required, visible, validating } = this.props
        const value = this.props.values[name]
        const errors = this.props.errors[name]

        let showError = false
        if (errors && errors.length && validating) {
            showError = true
        }

        const childProps = { id: name, onChange: this.handleChange, name: name, error: showError }
        if (form.props.control && form.props.control.name === 'Checkbox') {
            childProps['checked'] = value
        } else {
            childProps['value'] = value
        }

        return (
            visible && (
                <Grid columns={3} container>
                    <Grid.Column verticalAlign='middle' width={4}>
                        <Form.Field required={required} label={{ children: label, htmlFor: name }} />
                    </Grid.Column>
                    <Grid.Column verticalAlign='middle' width={8}>
                        {React.cloneElement(form, childProps)}
                    </Grid.Column>
                    <Grid.Column verticalAlign='middle' width={4}>
                        {showError ? <Label basic pointing='left' color='red' content={assembleErrorString(errors)} /> : null}
                    </Grid.Column>
                </Grid>
            )
        )
    }
}

export { FormController, FormField }