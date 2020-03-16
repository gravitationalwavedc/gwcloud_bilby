import React from "react";
import {Grid} from "semantic-ui-react";
import {harnessApi} from "../index";
import StepForm from "../Components/StepForm";
import { graphql, QueryRenderer } from "react-relay";

class BilbyJobList extends React.Component {
    constructor() {
        super();
    }

    renderForms = ({error, props}) => {
        if (error) {
            return <div>{error.message}</div>
        } else if (props) {
            return (
                <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                    {this.props.username}
                </Grid>
            )
        }
    }

    render() {
        return <div>hello</div>
        // return <QueryRenderer
        //     environment={harnessApi.getEnvironment('bilby')}
        //     query={graphql`
        //         query Routes_UserDetails_Query {
        //             gwclouduser {
        //                 username
        //             }
        //         }
        //     `}
        //     render={this.renderForms}
        // />
    }
}