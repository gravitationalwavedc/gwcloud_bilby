import React from "react";
import {Grid, Segment, Button} from "semantic-ui-react";
import Link from 'found/lib/Link';
import BilbyBasePage from "./BilbyBasePage";
import { createFragmentContainer, graphql } from "react-relay";
import PublicJobList from "../Components/List/PublicJobList";

class BilbyHomePage extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: null
        }
    }

    render() {
        return (
            <BilbyBasePage loginRequired title="Welcome to Bilby" {...this.routing}>
                <Grid.Row>
                    <Segment>
                        Welcome to Bilby!
                    </Segment>
                </Grid.Row>
                <Grid.Row>
                    <Link to={'/bilby/job-form/'} exact {...this.props}>
                        <Button>Create new job</Button>
                    </Link>
                    <Link to={'/bilby/job-list/'} exact {...this.props}>
                        <Button>Job list</Button>
                    </Link>
                </Grid.Row>
                <PublicJobList data={this.props.data} {...this.routing}/>
            </BilbyBasePage>
        )
    }
}

// export default BilbyHomePage;
export default createFragmentContainer(BilbyHomePage, {
    data: graphql`
        fragment BilbyHomePage_data on Query {
            ...PublicJobList_data
        }
    `
});