import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, longerThan, shorterThan} from "../Utils/errors";


class SubmitForm extends React.Component {
    constructor(props) {
        super(props);

    }


    render() {
        return (
            <React.Fragment>
                <Grid.Row columns={2}>
                    <Grid.Column floated='right'>
                        <Button onClick={this.props.onSubmit}>Submit Job</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default SubmitForm;