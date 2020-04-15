import React from "react";
import {Grid, Button} from "semantic-ui-react";


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