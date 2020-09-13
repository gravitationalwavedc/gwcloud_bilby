import React from "react";
import {Grid, Segment, Button, Header} from "semantic-ui-react";
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
                    <Header>Welcome to Bilby!</Header>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column width={15}>
                        <PublicJobList data={this.props.data} {...this.routing}/>
                    </Grid.Column>
                </Grid.Row>
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