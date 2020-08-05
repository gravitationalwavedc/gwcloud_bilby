import React from "react";
import {Grid, Button, Message} from "semantic-ui-react";
import * as Enumerable from "linq";


class SubmitForm extends React.Component {
    constructor(props) {
        super(props);

    }


    render() {
        let errors = null;
        if (this.props.errors)
            errors = Enumerable.from(this.props.errors).select((e, i) => (
                <Message error key={i}>
                    {e.message}
                </Message>
            )) 

        return (
            <React.Fragment>
                {this.props.errors ? (
                    <Grid.Row>
                        {errors}
                    </Grid.Row>
                ) : null
                }
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.props.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.props.onSubmit}>Submit Job</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default SubmitForm;